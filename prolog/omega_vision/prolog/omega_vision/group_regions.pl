% Source: logicmoo/omega_vision/prolog/omega_vision/group_regions.pl
% Original SHA-256: 76d86beeebc9da98624569cc412e5f5222d2a70420f5e7b54e83ae8c74092961
% LGPL-2.1-or-later. Standalone streaming adapter in pipeline_bridge.pl.
% group_regions.pl — bbox-FREE symbolic grouping over topological region facts
% from pixels_to_regions.py.  Containment comes from `encloses/2` (one region
% fully surrounds another) and object instances from connected components of
% `adjacent/2` (pixels actually touch).  No bounding boxes are ever used.
%
% Facts consumed:
%   region(Id, Color, Area, centroid(CX,CY)).
%   adjacent(A, B).  shared_edge(A, B, Pixels).
%   encloses(Outer, Inner).  border(Id).  img_size(W, H).
%   polygon(Id, Pts).  hole(Id, Pts).  midline(Id, Pts).
%   fillpoint(Id, xy(X,Y), Depth).
%
% Run: swipl -q -g "consult('group_regions.pl'), consult('REGIONS.pl'), report" -t halt

:- dynamic region/4.
:- dynamic adjacent/2.
:- dynamic shared_edge/3.
:- dynamic encloses/2.
:- dynamic border/1.
:- dynamic img_size/2.
:- dynamic perimeter/2.
:- dynamic polygon/2.
:- dynamic hole/2.
:- dynamic midline/2.
:- dynamic fillpoint/3.

% ---- parts map: the FIRST artifact Prolog produces --------------------------
% Every part as simplified boundary polygons, OUTER edge (silhouette,
% polygon/2) separate from INNER edges (holes, hole/2): part_map/1 lists
% part(Id, Color, Area, Centroid, Outer, Holes), largest first.
part_map(Parts) :-
    findall(Area-part(Id, Color, Area, Centroid, Outer, Holes),
            ( region(Id, Color, Area, Centroid),
              polygon(Id, Outer),
              findall(H, hole(Id, H), Holes) ),
            Keyed),
    sort(1, @>=, Keyed, Sorted),
    findall(P, member(_-P, Sorted), Parts).

part(Id, Color, Area, Centroid) :- region(Id, Color, Area, Centroid).

% ---- background: exterior plus matching-color regions in exposed cutouts -----
% The exterior background hugs the image edge and is large. If a foreground
% region touches it, a same-color region filling one of that region's cutouts
% is background too rather than a detachable foreground part.
exterior_background(Id) :-
    border(Id),
    img_size(W, H),
    region(Id, _, Area, _),
    Area >= 0.10 * W * H.

background(Id) :- exterior_background(Id).
background(Inner) :-
    exterior_background(Bg),
    adj(Outer, Bg),
    region(Bg, Color, _, _),
    region(Inner, Color, _, _),
    in_cutout(Inner, Outer, _).

foreground(Id) :- region(Id, _, _, _), \+ background(Id).

% ---- containment: straight from topology, no boxes -------------------------
part_of(Inner, Outer) :- encloses(Outer, Inner).

group(Outer, Inners) :-
    findall(I, encloses(Outer, I), Inners),
    Inners \== [].

% ---- object instances: connected components of touch adjacency -------------
adj(A, B) :- adjacent(A, B).
adj(A, B) :- adjacent(B, A).
nadj(A, B) :- adj(A, B), \+ background(A), \+ background(B).

% ---- part groups: strong exact-edge attachment ------------------------------
% Two parts belong to one group when they share an exact edge long enough to
% mean "attached" (a hairline lying along a face shares a long boundary), and
% groups chain onward through members that share edges leading away from the
% others (hair -> face -> body). Purely topological; never a box.
strong_edge_pct(1).

:- dynamic strong_edge_pct_override/1.
current_strong_edge_pct(Pct) :-
    ( strong_edge_pct_override(P), number(P) -> Pct = P ; strong_edge_pct(Pct) ).

sedge(A, B, N) :- shared_edge(A, B, N).
sedge(A, B, N) :- shared_edge(B, A, N).

% Scale-invariant attachment: the shared edge must be at least Pct% of the
% smaller region's perimeter (upscaling multiplies edge and perimeter alike).
strong_adj(A, B) :-
    sedge(A, B, N),
    \+ background(A),
    \+ background(B),
    perimeter(A, PA),
    perimeter(B, PB),
    Min is min(PA, PB),
    Min > 0,
    current_strong_edge_pct(Pct),
    N * 100 >= Pct * Min.

% ---- squarish: compact tile-like silhouette (bbox-free) ----------------------
% A square's perimeter^2/area is 16; organic silhouettes score far higher.
% Gridded tiles are squarish and are NOT pulled into a group by enclosure.
squarish(Id) :-
    region(Id, _, Area, _),
    Area > 0,
    perimeter(Id, P),
    Q is P * P / Area,
    Q >= 14.0,
    Q =< 18.0.

% Square OUTER silhouette: judged from the outer polygon ring only, so internal
% cutouts (glyph holes) do not inflate the score. A square box full of glyphs
% still reads as a square outer.
outer_squarish(Id) :-
    polygon(Id, Pts),
    ring_perimeter(Pts, P),
    ring_area(Pts, A),
    A > 0,
    Q is P * P / A,
    Q >= 14.0,
    Q =< 18.0.

% ---- attachment ---------------------------------------------------------------
% POSITIVE EVIDENCE ONLY: every clause below adds group evidence; nothing
% ever subtracts. Parts attach through strong exact edges, and through
% smooth cutouts: a region that fills another object's smooth-edged cutout
% belongs to that object's group (eyeholes for the face, mouthholes for
% mouths). Background cutouts are silhouettes: fillers of one smooth
% background hole group with each other, never with the background itself.
% A complex figure against a night sky qualifies for nothing precisely
% because its own outline made the sky's cutout too complex to pass the
% smoothness test - the rule self-disqualifies; the figure keeps only its
% own evidence. Cutout fillers stay detachable/1.
attached(A, B) :- strong_adj(A, B), crack_gate(A, B).
attached(Outer, Inner) :- nonbg_cutout(Outer, Inner).
attached(Inner, Outer) :- nonbg_cutout(Outer, Inner).
attached(Outer, Inner) :- glyphy_member(Outer, Inner).
attached(Inner, Outer) :- glyphy_member(Outer, Inner).
attached(A, B) :-
    background(Bg),
    in_smooth_cutout(A, Bg, Ring),
    in_smooth_cutout(B, Bg, Ring),
    A \== B,
    foreground(A),
    foreground(B).

nonbg_cutout(Outer, Inner) :-
    in_smooth_cutout(Inner, Outer, _),
    foreground(Outer),
    foreground(Inner).

% Inner fills the cutout Ring of Outer: enclosed, and a point of its fill lies
% inside that hole ring. Fillpoints are guaranteed interior (centroids are not:
% donuts, crescents), so probe those first.
in_cutout(Inner, Outer, Ring) :-
    encloses(Outer, Inner),
    inner_probe(Inner, CX, CY),
    hole(Outer, Ring),
    point_in_ring(CX, CY, Ring).

in_smooth_cutout(Inner, Outer, Ring) :-
    in_cutout(Inner, Outer, Ring),
    ring_smooth(Ring).

inner_probe(Inner, X, Y) :- fillpoint(Inner, xy(X, Y), _), !.
inner_probe(Inner, X, Y) :- region(Inner, _, _, centroid(X, Y)).

fills_cutout(Inner, Outer) :- in_smooth_cutout(Inner, Outer, _).

% ---- ring geometry: smoothness straight from the hole polygon ---------------
% Smooth means compact edge: perimeter^2/area near a circle's 4*pi (12.57);
% ellipses/eyeholes stay under ~20, ragged or hairline cutouts score far
% higher. Tiny rings are noise, not cutouts.
smooth_max_q(20.0).

ring_smooth(Points) :-
    length(Points, N), N >= 4,
    ring_area(Points, Area), Area >= 9,
    ring_perimeter(Points, P),
    Q is P * P / Area,
    smooth_max_q(Max),
    Q =< Max.

ring_perimeter([First|Rest], P) :-
    append([First|Rest], [First], Closed),
    seg_sum(Closed, 0.0, P).

seg_sum([_], Acc, Acc).
seg_sum([xy(X1,Y1), xy(X2,Y2)|T], Acc, P) :-
    D is sqrt((X2-X1)*(X2-X1) + (Y2-Y1)*(Y2-Y1)),
    Acc1 is Acc + D,
    seg_sum([xy(X2,Y2)|T], Acc1, P).

ring_area([First|Rest], Area) :-
    append([First|Rest], [First], Closed),
    shoelace(Closed, 0.0, S),
    Area is abs(S) / 2.

shoelace([_], Acc, Acc).
shoelace([xy(X1,Y1), xy(X2,Y2)|T], Acc, S) :-
    Acc1 is Acc + (X1*Y2 - X2*Y1),
    shoelace([xy(X2,Y2)|T], Acc1, S).

% ray casting: odd number of edge crossings to the right = inside
point_in_ring(X, Y, [First|Rest]) :-
    append([First|Rest], [First], Closed),
    crossings(Closed, X, Y, 0, C),
    1 is C mod 2.

crossings([_], _, _, Acc, Acc).
crossings([xy(X1,Y1), xy(X2,Y2)|T], X, Y, Acc, C) :-
    (   ( Y1 > Y, Y2 =< Y ; Y2 > Y, Y1 =< Y ),
        XI is X1 + (Y - Y1) * (X2 - X1) / (Y2 - Y1),
        X < XI
    ->  Acc1 is Acc + 1
    ;   Acc1 = Acc
    ),
    crossings([xy(X2,Y2)|T], X, Y, Acc1, C).

detachable(Inner) :- encloses(_, Inner), \+ background(Inner).

scluster([], Acc, Sorted) :- sort(Acc, Sorted).
scluster([X|Q], Acc, Out) :-
    ( memberchk(X, Acc)
    -> scluster(Q, Acc, Out)
    ;  findall(Y, (attached(X, Y), \+ memberchk(Y, Acc)), Ns),
       append(Q, Ns, Q1),
       scluster(Q1, [X|Acc], Out)
    ).

:- dynamic w_engine_mode/1.

part_groups(Groups) :-
    findall(Id, foreground(Id), Ids),
    partition_part_groups(Ids, [], Raw),
    regroup_by_color(Raw, Colored),
    ( w_engine_mode("old")
    -> Groups = Colored
    ;  extract_solo_cutouts(Colored, Base),
       child_groups(ChildGroups),
       append(Base, ChildGroups, Groups)
    ).

% Extra child groups: the enclosed contents of each glyphy square box, emitted
% as their own group in ADDITION to the whole-box group (parent Wn + child Wm).
child_groups(Groups) :-
    findall(Inners, ( glyphy_enclosure(O), enclosed_inners(O, Inners), Inners \== [] ), Gs0),
    sort(Gs0, Groups).

% ---- LOCAL HACK (not in upstream group_regions.pl) --------------------------
% Canonical "fully enclosed": Inner sits in a cutout (hole) of Outer AND Outer's
% overall silhouette is squarish (a square box/tile with something inside it).
% Such a single fully-enclosed Inner is pulled OUT into its own singleton W
% group. Only fires when exactly one region is fully enclosed by that Outer; if
% two or more qualify for the same Outer, none are pulled and they stay merged.
fully_enclosed(Outer, Inner) :-
    in_cutout(Inner, Outer, _),
    foreground(Outer),
    foreground(Inner),
    outer_squarish(Outer).

enclosed_inners(Outer, Inners) :-
    findall(I, held_inside(I, Outer), Is),
    sort(Is, Inners).

% held_inside: enclosure evidence for glyph/readout content. Either the classic
% cutout (hole ring) proof, or pocket enclosure for content the extractor could
% not certify individually (chained fillers, border-clipped last segment).
held_inside(Inner, Outer) :- in_cutout(Inner, Outer, _).
held_inside(Inner, Outer) :- pocket_member(Outer, Inner).

% A pocket of Outer is the connected set reachable from Inner without crossing
% Outer. The set is genuinely held inside Outer when it touches Outer, contains
% no background, touches the image border only when Outer itself is
% border-clipped, and is smaller than Outer (a pocket, not the rest of the
% scene). This certifies chained fillers (green + track) and a last segment
% clipped by the frame edge, which single-region enclosure can never certify.
pocket_member(Outer, Inner) :-
    foreground(Outer),
    foreground(Inner),
    Inner \== Outer,
    pocket_closure([Inner], Outer, [], Cluster),
    \+ ( member(M, Cluster), background(M) ),
    \+ ( member(M, Cluster), border(M), \+ border(Outer) ),
    \+ \+ ( member(M, Cluster), adj(M, Outer) ),
    region(Outer, _, OuterArea, _),
    cluster_area(Cluster, PocketArea),
    PocketArea < OuterArea.

pocket_closure([], _, Acc, Cluster) :- sort(Acc, Cluster).
pocket_closure([X|Q], Outer, Acc, Cluster) :-
    ( memberchk(X, Acc)
    -> pocket_closure(Q, Outer, Acc, Cluster)
    ;  findall(Y, (adj(X, Y), Y \== Outer, \+ memberchk(Y, Acc)), Ns),
       append(Q, Ns, Q1),
       pocket_closure(Q1, Outer, [X|Acc], Cluster)
    ).

cluster_area(Cluster, Area) :-
    findall(A, (member(M, Cluster), region(M, _, A, _)), As),
    sum_list(As, Area).

% glyphy: a square-OUTLINE box whose inside is glyph-like content — two or more
% enclosed regions, or a single enclosed region with a complex (non-squarish)
% outline.
glyphy_enclosure(Outer) :-
    foreground(Outer),
    outer_squarish(Outer),
    enclosed_inners(Outer, Inners),
    ( Inners = [_, _|_]
    ; Inners = [Single], \+ squarish(Single)
    ).

% HUD readout: an elongated (non-squarish) container whose cutouts hold two or
% more inner regions — an energy bar, meter, or status strip — is treated like
% a glyphed box / readout: the container and its segments form ONE W group,
% with each segment also emitted as a child object. Readout contents nearly
% fill their frame; a sparse pocket (a playfield holding a few pieces) does not.
glyphy_enclosure(Outer) :-
    foreground(Outer),
    \+ outer_squarish(Outer),
    enclosed_inners(Outer, Inners),
    Inners = [_, _|_],
    cluster_area(Inners, InnerArea),
    region(Outer, _, OuterArea, _),
    InnerArea * 2 >= OuterArea.

% Keep a glyphy box and everything inside it as ONE W group (non-old modes).
glyphy_member(Outer, Inner) :-
    \+ w_engine_mode("old"),
    glyphy_enclosure(Outer),
    held_inside(Inner, Outer).

% Each enclosed glyph is also its own child object of the container.
child_of(Inner, Outer) :-
    glyphy_enclosure(Outer),
    held_inside(Inner, Outer).

% Solo pull-out only for a simple single fully-enclosed inner (never glyphy).
solo_cutout(Inner) :-
    fully_enclosed(Outer, Inner),
    \+ glyphy_enclosure(Outer),
    findall(X, fully_enclosed(Outer, X), Xs0),
    sort(Xs0, [Inner]).

extract_solo_cutouts(Groups, Out) :-
    findall(R, solo_cutout(R), Solos0),
    sort(Solos0, Solos),
    ( Solos == []
    -> Out = Groups
    ;  remove_members(Groups, Solos, Trimmed),
       findall([R], member(R, Solos), SoloGroups),
       append(Trimmed, SoloGroups, Out)
    ).

remove_members([], _, []).
remove_members([G|T], Solos, Out) :-
    subtract(G, Solos, G1),
    remove_members(T, Solos, Rest),
    ( G1 == [] -> Out = Rest ; Out = [G1|Rest] ).
% ---- END LOCAL HACK ---------------------------------------------------------

% ---- LOCAL HACK: crack continuity (~180 deg junction) -----------------------
% Only active in w_engine_mode("crack"). A strong shared edge is treated as a
% real merge only when, at BOTH ends of the shared boundary, the two regions'
% outer outlines continue ~180 deg apart (the silhouette runs straight through
% the crack tip). A chain of tiles that merely touch fails this and stays apart;
% an egg split by a jagged crack passes and joins. Reuses heading/5 (turtle).
crack_angle_tol(40).
crack_near_tol(3).

:- dynamic crack_angle_tol_override/1.
current_crack_angle_tol(Tol) :-
    ( crack_angle_tol_override(T), number(T) -> Tol = T ; crack_angle_tol(Tol) ).

crack_gate(A, B) :-
    ( w_engine_mode("crack")
    -> catch(crack_continuous(A, B), _, fail)
    ;  true
    ).

near_pt(xy(X1, Y1), xy(X2, Y2)) :-
    crack_near_tol(T),
    abs(X1 - X2) =< T,
    abs(Y1 - Y2) =< T.

shared_on(Pts, Other, P) :-
    member(P, Pts),
    once(( member(PB, Other), near_pt(P, PB) )).

% neighbours of a point on a closed ring (by index, wrapping)
ring_neighbours(Pts, xy(X, Y), Prev, Next) :-
    nth0(I, Pts, xy(X, Y)), !,
    length(Pts, N),
    Ip is (I - 1 + N) mod N, nth0(Ip, Pts, Prev),
    In is (I + 1) mod N, nth0(In, Pts, Next).

% direction the outline leaves a tip: the neighbour that is NOT alongside Other
leaving_heading(Pts, Other, Tip, H) :-
    ring_neighbours(Pts, Tip, Prev, Next),
    ( \+ ( member(PB, Other), near_pt(Next, PB) )
    -> Tip = xy(TX, TY), Next = xy(NX, NY), heading(TX, TY, NX, NY, H)
    ;  Tip = xy(TX, TY), Prev = xy(PX, PY), heading(TX, TY, PX, PY, H)
    ).

opposite(HA, HB) :-
    D0 is HA - HB,
    D1 is D0 - 360 * round(D0 / 360),
    Diff is abs(D1),
    current_crack_angle_tol(Tol),
    Diff >= 180 - Tol,
    Diff =< 180 + Tol.
crack_continuous(A, B) :-
    polygon(A, PtsA), PtsA \== [],
    polygon(B, PtsB), PtsB \== [],
    findall(P, shared_on(PtsA, PtsB, P), SharedA0),
    sort(SharedA0, SharedA),
    length(SharedA, NS), NS >= 2,
    farthest_pair(SharedA, Tip1, Tip2),
    tip_ok(PtsA, PtsB, Tip1),
    tip_ok(PtsA, PtsB, Tip2).

tip_ok(PtsA, PtsB, TipA) :-
    leaving_heading(PtsA, PtsB, TipA, HA),
    nearest(PtsB, TipA, TipB),
    leaving_heading(PtsB, PtsA, TipB, HB),
    opposite(HA, HB).

farthest_pair(Points, P1, P2) :-
    findall(D-(A-B),
            ( member(A, Points), member(B, Points), A @< B,
              A = xy(AX, AY), B = xy(BX, BY),
              D is (AX - BX) * (AX - BX) + (AY - BY) * (AY - BY) ),
            Pairs),
    Pairs \== [],
    keysort(Pairs, Sorted),
    last(Sorted, _-(P1-P2)).

nearest(Points, xy(X, Y), Best) :-
    findall(D-P,
            ( member(P, Points), P = xy(PX, PY),
              D is (PX - X) * (PX - X) + (PY - Y) * (PY - Y) ),
            Ds),
    keysort(Ds, [_-Best|_]).
% ---- END LOCAL HACK ---------------------------------------------------------

% ---- color regrouping: a merged group whose members span several colors,
% with two or more of those colors contributing two or more parts each, is
% really several color-keyed siblings glued together (tile grids, mosaics).
% Split such a group into one group per color. Groups where at most one
% color repeats (a face with two same-color eyes, an outline with one odd
% accent) stay merged.
regroup_by_color([], []).
regroup_by_color([G|T], Out) :-
    split_mixed_group(G, Parts),
    regroup_by_color(T, Rest),
    append(Parts, Rest, Out).

% A very large color mass is a structural object in its own right. Remove it
% before clustering attached details so it cannot bridge unrelated parts.
split_mixed_group(Members, Split) :-
    split_dominant_color_mass(Members, Split),
    !.
split_mixed_group(Members, Split) :-
    group_color_census(Members, Census),
    include([_-Ids]>>(length(Ids, N), N >= 2), Census, Multi),
    length(Multi, NM),
    NM >= 2,
    !,
    findall(Ids, member(_-Ids, Census), Split).
split_mixed_group(Members, [Members]).

dominant_color_min_group_percent(67).
dominant_color_min_image_percent(10).

split_dominant_color_mass(Members, [MassMembers|OtherGroups]) :-
    dominant_color_mass(Members, Color),
    include(region_has_color(Color), Members, MassMembers),
    exclude(region_has_color(Color), Members, OtherMembers),
    MassMembers \== [],
    OtherMembers \== [],
    partition_attached_subset(OtherMembers, RawOtherGroups),
    regroup_by_color(RawOtherGroups, OtherGroups).

dominant_color_mass(Members, Color) :-
    group_color_areas(Members, ColorAreas),
    keysort(ColorAreas, Ascending),
    reverse(Ascending, [ColorArea-Color|_]),
    member_area_sum(Members, GroupArea),
    img_size(Width, Height),
    ImageArea is Width * Height,
    dominant_color_min_group_percent(GroupPercent),
    dominant_color_min_image_percent(ImagePercent),
    ColorArea * 100 >= GroupArea * GroupPercent,
    ColorArea * 100 >= ImageArea * ImagePercent.

group_color_areas(Members, ColorAreas) :-
    findall(Color,
            ( member(Id, Members),
              region(Id, Color, _, _)
            ),
            RawColors),
    sort(RawColors, Colors),
    findall(Area-Color,
            ( member(Color, Colors),
              include(region_has_color(Color), Members, ColorMembers),
              member_area_sum(ColorMembers, Area)
            ),
            ColorAreas).

region_has_color(Color, Id) :-
    region(Id, Color, _, _).

member_area_sum(Members, Area) :-
    findall(MemberArea,
            ( member(Id, Members),
              region(Id, _, MemberArea, _)
            ),
            Areas),
    sum_list(Areas, Area).

partition_attached_subset([], []).
partition_attached_subset([Seed|Rest], [Group|Groups]) :-
    scluster_within([Seed|Rest], Seed, Group),
    subtract(Rest, Group, Remaining),
    partition_attached_subset(Remaining, Groups).

scluster_within(Allowed, Seed, Members) :-
    scluster_within_([Seed], Allowed, [], Raw),
    sort(Raw, Members).

scluster_within_([], _, Seen, Seen).
scluster_within_([X|Queue], Allowed, Seen, Members) :-
    ( memberchk(X, Seen)
    -> scluster_within_(Queue, Allowed, Seen, Members)
    ;  findall(Y,
               ( attached(X, Y),
                 memberchk(Y, Allowed),
                 \+ memberchk(Y, Seen)
               ),
               Neighbors),
       append(Queue, Neighbors, Next),
       scluster_within_(Next, Allowed, [X|Seen], Members)
    ).

% Census: [Color-[MemberIds...]] for one group, colors sorted.
group_color_census(Members, Census) :-
    findall(C-Id, (member(Id, Members), region(Id, C, _, _)), Pairs),
    keysort(Pairs, SortedPairs),
    group_pairs_by_key(SortedPairs, Census).

partition_part_groups([], _, []).
partition_part_groups([Id|T], Seen, Out) :-
    ( memberchk(Id, Seen)
    -> partition_part_groups(T, Seen, Out)
    ;  scluster([Id], [], Members),
       append(Members, Seen, Seen1),
       Out = [Members|Rest],
       partition_part_groups(T, Seen1, Rest)
    ).

cluster([], Acc, Sorted) :- sort(Acc, Sorted).
cluster([X|Q], Acc, Out) :-
    ( memberchk(X, Acc)
    -> cluster(Q, Acc, Out)
    ;  findall(Y, (nadj(X, Y), \+ memberchk(Y, Acc)), Ns),
       append(Q, Ns, Q1),
       cluster(Q1, [X|Acc], Out)
    ).

objects(Objects) :-
    findall(Id, foreground(Id), Ids),
    partition_objects(Ids, [], Objects).

partition_objects([], _, []).
partition_objects([Id|T], Seen, Objs) :-
    ( memberchk(Id, Seen)
    -> partition_objects(T, Seen, Objs)
    ;  cluster([Id], [], Members),
       append(Members, Seen, Seen1),
       Objs = [Members|Rest],
       partition_objects(T, Seen1, Rest)
    ).

% ---- report ----------------------------------------------------------------
report :-
    aggregate_all(count, region(_,_,_,_), NR),
    aggregate_all(count, encloses(_,_), NE),
    findall(Id, background(Id), Bg0), sort(Bg0, Bg), length(Bg, NB),
    objects(Objs), length(Objs, NO),
    part_groups(Groups),
    include([G]>>(length(G, LG), LG >= 2), Groups, RealGroups),
    length(RealGroups, NG),
    format("~n== ~w regions, ~w enclosures, ~w background, ~w objects, ~w part groups ==~n",
           [NR, NE, NB, NO, NG]),
    part_map(Parts), length(Parts, NP),
    aggregate_all(count, midline(_, _), NM),
    format("~n== parts map (~w polygons, outer + holes, ~w midlines, largest first) ==~n", [NP, NM]),
    forall((nth1(I, Parts, part(Id, Col, Area, _, Outer, Holes)), I =< 12),
           ( length(Outer, NPts), length(Holes, NH),
             aggregate_all(count, midline(Id, _), NMid),
             format("  ~w (~w, ~w px): ~w-gon, ~w hole(s), ~w midline(s)~n", [Id, Col, Area, NPts, NH, NMid]) )),
    format("~n== containment groups (encloses) ==~n"),
    forall((group(P, Cs), length(Cs, L), L >= 1),
           ( region(P, Col, _, _), format("  ~w (~w) encloses ~w~n", [P, Col, Cs]) )),
    format("~n== part groups (strong exact-edge attachment) ==~n"),
    forall(member(G, RealGroups),
           ( length(G, LG),
             aggregate_all(sum(A), (member(M, G), region(M, _, A, _)), Area),
             findall(D, (member(D, G), detachable(D)), Ds),
             ( Ds == []
             -> format("  group of ~w parts (~w px): ~w~n", [LG, Area, G])
             ;  format("  group of ~w parts (~w px): ~w  detachable: ~w~n", [LG, Area, G, Ds]) ) )),
    format("~n== object instances (adjacency clusters, foreground) ==~n"),
    forall((member(M, Objs), length(M, L), L >= 3),
           format("  object of ~w regions: ~w~n", [L, M])).

    % ---- machine output ----------------------------------------------------------
    % write_groups(+File): apply the grouping rules to the consulted parts-map
    % facts and write the conclusions as facts for the next pipeline step.
    % This is the prolog doer behind the part_groups transformation
    % (<move>/part_groups/prolog/groups.pl).
    write_groups(File) :-
        setup_call_cleanup(open(File, write, S), write_groups_stream(S), close(S)).

    write_groups_stream(S) :-
        format(S, "% part_groups by group_regions.pl (prolog doer)~n", []),
        forall(member(N/A, [part_group/2, group_area/2, background/1, detachable/1,
                            object_instance/2, part_of/2, squarish/1, child_of/2]),
               format(S, ":- dynamic ~w/~w.~n:- discontiguous ~w/~w.~n", [N, A, N, A])),
        part_groups(Groups),
        forall(nth1(I, Groups, G),
               ( format(S, "part_group(w~w, ~w).~n", [I, G]),
                 aggregate_all(sum(Ar), (member(M, G), region(M, _, Ar, _)), Area),
                 format(S, "group_area(w~w, ~w).~n", [I, Area]) )),
        findall(B, background(B), Bs0), sort(Bs0, Bs),
        forall(member(B, Bs), format(S, "background(~w).~n", [B])),
        findall(D, detachable(D), Ds0), sort(Ds0, Ds),
        forall(member(D, Ds), format(S, "detachable(~w).~n", [D])),
        objects(Objs),
        forall(nth1(J, Objs, O), format(S, "object_instance(o~w, ~w).~n", [J, O])),
        findall(In-Out, part_of(In, Out), Ps0), sort(Ps0, Ps),
        forall(member(In-Out, Ps), format(S, "part_of(~w, ~w).~n", [In, Out])),
        findall(Q, squarish(Q), Qs0), sort(Qs0, Qs),
        forall(member(Q, Qs), format(S, "squarish(~w).~n", [Q])),
        findall(In2-Out2, child_of(In2, Out2), Cs0), sort(Cs0, Cs),
        forall(member(In2-Out2, Cs), format(S, "child_of(~w, ~w).~n", [In2, Out2])).
