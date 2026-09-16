% Source: logicmoo/omega_vision/prolog/omega_vision/shape_finder.pl
% Original SHA-256: 0ae4553d828b1236f2b32e2ea78e9b6baa75d0595403040d11d337d385c3fab8
% LGPL-2.1-or-later. Standalone streaming adapter in pipeline_bridge.pl.
%% shape_finder.pl — pure-Prolog shape finder (shape_finder_prolog doer).
%%
%% Input: a quantized pixel grid as cell(X, Y, Color) facts plus
%% grid_size(W, H), consulted before write_parts/1 runs. Output: the same
%% fact schema the python doers emit so downstream rules and comparisons
%% consume any doer unchanged:
%%
%%   region(Id, Color, Area, centroid(CX, CY)).
%%   polygon(Id, [xy(X,Y), ...]).      % OUTER EDGE (closed ring)
%%   hole(Id, [xy(X,Y), ...]).         % INNER EDGES (one per cutout)
%%   midline(Id, [xy(X,Y), ...]).      % INNER MEDIALS (distance-ridge paths)
%%   fillpoint(Id, xy(X,Y), Depth).    % fill peaks, deepest first
%%   adjacent(A, B). shared_edge(A, B, N). img_size(W, H).
%%
%% Regions are 4-connected same-color components. The outer edge walks the
%% region's boundary pixels; holes are enclosed complement components; the
%% medial is the crest of a multi-source BFS distance field seeded at the
%% boundary. Everything is plain Prolog over assoc/ordsets — the point of
%% this doer is symbolic comparability, not raw speed.

%% Plain user-module file (no module/2): the pixel grid (cell/3, grid_size/2)
%% is consulted as user facts right next to these rules, so everything
%% resolves in one namespace when swipl runs write_parts/1.

:- use_module(library(assoc)).
:- use_module(library(lists)).
:- use_module(library(apply)).
:- use_module(library(pairs)).

:- dynamic cell/3.
:- dynamic grid_size/2.

%% ---- pixel access -------------------------------------------------------

pixel_color(X-Y, C) :- cell(X, Y, C).

neighbor4(X-Y, NX-NY) :-
    member(DX-DY, [1-0, -1-0, 0-1, 0-(-1)]),
    NX is X + DX, NY is Y + DY.

neighbor8(X-Y, NX-NY) :-
    member(DX-DY, [1-0, -1-0, 0-1, 0-(-1), 1-1, 1-(-1), -1-1, -1-(-1)]),
    NX is X + DX, NY is Y + DY.

%% ---- region flood fill ---------------------------------------------------

%% regions(-Regions): Regions = list of region(Id, Color, PixelOrdset).
regions(Regions) :-
    findall(P-C, (cell(X, Y, C), P = X-Y), Cells),
    list_to_assoc(Cells, ColorOf),
    empty_assoc(Claimed),
    foldl(flood_cell(ColorOf), Cells, s([], Claimed, 0), s(Rev, _, _)),
    reverse(Rev, Tagged),
    findall(region(Id, Color, Pix),
            member(r(Id, Color, Pix), Tagged),
            Regions).

flood_cell(ColorOf, P-C, s(Acc, Claimed, N), s(Acc2, Claimed2, N2)) :-
    (   get_assoc(P, Claimed, _)
    ->  Acc2 = Acc, Claimed2 = Claimed, N2 = N
    ;   flood_from(ColorOf, C, [P], Claimed, Claimed2, PixList),
        sort(PixList, Pix),
        N2 is N + 1,
        atom_concat(r, N2, Id),
        Acc2 = [r(Id, C, Pix) | Acc]
    ).

flood_from(_, _, [], Seen, Seen, []).
flood_from(ColorOf, C, [P | Queue], Seen, SeenOut, Out) :-
    (   get_assoc(P, Seen, _)
    ->  flood_from(ColorOf, C, Queue, Seen, SeenOut, Out)
    ;   put_assoc(P, Seen, true, Seen2),
        findall(NP, (neighbor4(P, NP), get_assoc(NP, ColorOf, C), \+ get_assoc(NP, Seen2, _)), Next),
        append(Queue, Next, Queue2),
        Out = [P | Rest],
        flood_from(ColorOf, C, Queue2, Seen2, SeenOut, Rest)
    ).

%% ---- region stats --------------------------------------------------------

centroid(Pix, CX, CY) :-
    length(Pix, N), N > 0,
    aggregate_all(sum(X), member(X-_, Pix), SX),
    aggregate_all(sum(Y), member(_-Y, Pix), SY),
    CX is round(SX / N), CY is round(SY / N).

%% ---- outer edge (boundary ring) ------------------------------------------

%% boundary pixel: a region pixel with a 4-neighbor outside the region.
boundary_pixels(PixSet, Boundary) :-
    include([P]>>(neighbor4(P, NP), \+ ord_memberchk(NP, PixSet)), PixSet, Boundary).

%% Trace the boundary into a ring by greedy nearest-neighbor walking over
%% the boundary pixel set (adequate for the quantized grids this doer runs
%% on; straight runs are compressed afterwards).
trace_ring(Boundary, Ring) :-
    Boundary = [Start | _],
    walk_ring(Start, [Start], Boundary, RevRing),
    reverse(RevRing, Ring0),
    compress_collinear(Ring0, Ring).

walk_ring(P, Path, Boundary, Out) :-
    subtract(Boundary, Path, Remaining),
    (   nearest8(P, Remaining, Next)
    ->  walk_ring(Next, [Next | Path], Boundary, Out)
    ;   Out = Path
    ).

nearest8(P, Pool, Next) :-
    findall(D-Q, (member(Q, Pool), chess_distance(P, Q, D), D =< 2), Cands),
    sort(Cands, [_-Next | _]).

chess_distance(X1-Y1, X2-Y2, D) :-
    D is max(abs(X1 - X2), abs(Y1 - Y2)).

%% drop midpoints of straight runs so rings stay small.
compress_collinear([], []).
compress_collinear([P], [P]).
compress_collinear([P, Q], [P, Q]).
compress_collinear([X1-Y1, X2-Y2, X3-Y3 | T], Out) :-
    (   (X2 - X1) * (Y3 - Y2) =:= (X3 - X2) * (Y2 - Y1)
    ->  compress_collinear([X1-Y1, X3-Y3 | T], Out)
    ;   Out = [X1-Y1 | Rest],
        compress_collinear([X2-Y2, X3-Y3 | T], Rest)
    ).

%% ---- inner edges (holes) --------------------------------------------------

%% Complement components inside the region's bbox that never touch the bbox
%% border are enclosed by the region: each one's pixels adjacent to the
%% region form an inner edge.
holes(PixSet, Holes) :-
    bbox(PixSet, X0, Y0, X1, Y1),
    findall(P, (between(Y0, Y1, Y), between(X0, X1, X), P = X-Y,
                \+ ord_memberchk(P, PixSet)), CompList),
    sort(CompList, Comp),
    complement_components(Comp, Groups),
    include(enclosed_group(X0, Y0, X1, Y1), Groups, Enclosed),
    findall(Ring,
            (member(G, Enclosed), boundary_of_group(G, PixSet, B), B \== [],
             trace_ring(B, Ring0), close_ring(Ring0, Ring)),
            Holes).

bbox(PixSet, X0, Y0, X1, Y1) :-
    aggregate_all(min(X), member(X-_, PixSet), X0),
    aggregate_all(max(X), member(X-_, PixSet), X1),
    aggregate_all(min(Y), member(_-Y, PixSet), Y0),
    aggregate_all(max(Y), member(_-Y, PixSet), Y1).

complement_components([], []).
complement_components([P | Rest], [Group | Groups]) :-
    comp_flood([P], [P | Rest], [], GroupList),
    sort(GroupList, Group),
    ord_subtract([P | Rest], Group, Remaining),
    complement_components(Remaining, Groups).

comp_flood([], _, Seen, Seen).
comp_flood([P | Q], Pool, Seen, Out) :-
    (   ord_memberchk(P, Seen)
    ->  comp_flood(Q, Pool, Seen, Out)
    ;   ord_add_element(Seen, P, Seen2),
        findall(NP, (neighbor4(P, NP), ord_memberchk(NP, Pool), \+ ord_memberchk(NP, Seen2)), Next),
        append(Q, Next, Q2),
        comp_flood(Q2, Pool, Seen2, Out)
    ).

enclosed_group(X0, Y0, X1, Y1, Group) :-
    \+ ( member(X-Y, Group),
         ( X =:= X0 ; X =:= X1 ; Y =:= Y0 ; Y =:= Y1 ) ).

%% a hole's ring: complement pixels 4-adjacent to the region.
boundary_of_group(Group, PixSet, Boundary) :-
    include([P]>>(neighbor4(P, NP), ord_memberchk(NP, PixSet)), Group, Boundary).

close_ring([], []).
close_ring([P | T], Ring) :-
    append([P | T], [P], Ring).

%% ---- inner medials (distance-ridge paths) ---------------------------------

%% Multi-source BFS from the boundary: depth 1 at the boundary, +1 inward.
distance_map(PixSet, Boundary, DistAssoc) :-
    findall(P-1, member(P, Boundary), Seeds),
    list_to_assoc(Seeds, Init),
    bfs_layers(Boundary, 1, PixSet, Init, DistAssoc).

bfs_layers([], _, _, Dist, Dist).
bfs_layers(Frontier, D, PixSet, Dist, Out) :-
    D2 is D + 1,
    findall(NP,
            (member(P, Frontier), neighbor4(P, NP),
             ord_memberchk(NP, PixSet), \+ get_assoc(NP, Dist, _)),
            NextList),
    sort(NextList, Next),
    foldl([P, A0, A]>>put_assoc(P, A0, D2, A), Next, Dist, Dist2),
    bfs_layers(Next, D2, PixSet, Dist2, Out).

%% medial points: depth >= every 8-neighbor's depth, and depth > 1.
medial_points(PixSet, Dist, Medials) :-
    include([P]>>(get_assoc(P, Dist, D), D > 1,
                  \+ ( neighbor8(P, NP), get_assoc(NP, Dist, ND), ND > D )),
            PixSet, Medials).

%% chain medial points into polylines by greedy nearest-neighbor walking.
medial_paths([], _, []).
medial_paths(Points, Dist, [Path | Paths]) :-
    Points = [Start | _],
    walk_ring(Start, [Start], Points, RevPath),
    reverse(RevPath, Raw),
    compress_collinear(Raw, Path),
    subtract(Points, Raw, Rest),
    medial_paths(Rest, Dist, Paths).

%% deepest point stands in when the crest degenerates (e.g. a square).
fill_peaks(PixSet, Dist, Peaks) :-
    findall(D-P, (member(P, PixSet), get_assoc(P, Dist, D)), Pairs),
    sort(0, @>=, Pairs, Sorted),
    first_peaks(Sorted, 5, Peaks).

first_peaks([], _, []).
first_peaks(_, 0, []) :- !.
first_peaks([D-P | T], N, [D-P | Rest]) :-
    N2 is N - 1,
    first_peaks(T, N2, Rest).

%% ---- adjacency -------------------------------------------------------------

adjacencies(Regions, Pairs) :-
    findall(A-B,
            (member(region(IdA, _, PixA), Regions),
             member(region(IdB, _, _), Regions),
             IdA @< IdB,
             member(P, PixA), neighbor4(P, NP),
             region_of(Regions, NP, IdB),
             A = IdA, B = IdB),
            All),
    msort(All, Sorted),
    clumped(Sorted, Pairs).

region_of(Regions, P, Id) :-
    member(region(Id, _, Pix), Regions),
    ord_memberchk(P, Pix), !.

%% ---- output -----------------------------------------------------------------

write_parts(OutFile) :-
    setup_call_cleanup(
        open(OutFile, write, S),
        emit(S),
        close(S)).

emit(S) :-
    format(S, "% shape_finder_prolog: outer edges, inner edges, inner medials~n", []),
    forall(member(D, [region/4, polygon/2, hole/2, midline/2, fillpoint/3,
                      adjacent/2, shared_edge/3, img_size/2]),
           ( D = N/A, format(S, ":- dynamic ~w/~w.~n", [N, A]) )),
    ( grid_size(W, H) -> true ; W = 0, H = 0 ),
    format(S, "img_size(~w, ~w).~n~n", [W, H]),
    regions(Regions),
    forall(member(region(Id, Color, Pix), Regions),
           emit_region(S, Id, Color, Pix)),
    adjacencies(Regions, Pairs),
    forall(member((A-B)-N, Pairs),
           format(S, "adjacent(~w, ~w).~nshared_edge(~w, ~w, ~w).~n", [A, B, A, B, N])).

emit_region(S, Id, Color, Pix) :-
    length(Pix, Area),
    Area >= 4,
    centroid(Pix, CX, CY),
    format(S, "region(~w, '~w', ~w, centroid(~w,~w)).~n", [Id, Color, Area, CX, CY]),
    boundary_pixels(Pix, Boundary),
    ( Boundary \== [], trace_ring(Boundary, Ring0), close_ring(Ring0, Ring), length(Ring, RL), RL >= 3
    -> emit_points(S, polygon, Id, Ring)
    ;  true ),
    holes(Pix, Holes),
    forall(member(HR, Holes),
           ( length(HR, HL), HL >= 3 -> emit_points(S, hole, Id, HR) ; true )),
    distance_map(Pix, Boundary, Dist),
    medial_points(Pix, Dist, Medials),
    ( Medials \== []
    -> medial_paths(Medials, Dist, MPaths),
       forall(member(MP, MPaths), emit_points(S, midline, Id, MP))
    ;  true ),
    fill_peaks(Pix, Dist, Peaks),
    forall(member(D-(X-Y), Peaks),
           format(S, "fillpoint(~w, xy(~w,~w), ~w).~n", [Id, X, Y, D])).
emit_region(_, _, _, _).

emit_points(S, Functor, Id, Points) :-
    findall(T, (member(X-Y, Points), format(atom(T), "xy(~w,~w)", [X, Y])), Terms),
    atomic_list_concat(Terms, ',', Inner),
    format(S, "~w(~w, [~w]).~n", [Functor, Id, Inner]).
