% Standalone stdin/stdout adapter. No files or directories are written.
:- use_module(library(http/json)).
:- use_module(library(time)).
:- ensure_loaded('shape_finder.pl').
:- ensure_loaded('group_regions.pl').
:- ensure_loaded('turtle_programs.pl').
:- ensure_loaded('group_acceptance.pl').

main :-
    catch(
        ( json_read_dict(user_input, Input),
          call_with_time_limit(25, run_pipeline(Input, Output)),
          json_write_dict(current_output, Output, [width(0)]), nl ),
        Error,
        (print_message(error, Error), halt(1))).

run_pipeline(Input, Output) :-
    Input.mode == "accept", !,
    load_facts(Input.facts),
    current_frame_group_acceptance(Records, Rejections, ExactRejections),
    with_output_to(string(Facts), write_acceptance_stream(current_output, Records, Rejections, ExactRejections)),
    Output = _{acceptance_facts:Facts}.

run_pipeline(Input, Output) :-
    ( Input.mode == "prolog"
    -> Grid = Input.grid, Palette = Input.palette,
       length(Grid, H), Grid = [First|_], length(First, W),
       assertz(grid_size(W, H)),
       forall((nth0(Y, Grid, Row), nth0(X, Row, Index), nth0(Index, Palette, Hex)),
              (atom_string(Color, Hex), assertz(cell(X, Y, Color)))),
       with_output_to(string(InitialFacts), emit(current_output)),
       load_facts(InitialFacts),
       regions(RegionPixels),
       add_pixel_topology(RegionPixels, W, H),
       with_output_to(string(ExtraFacts), emit_extra_topology),
       string_concat(InitialFacts, ExtraFacts, Facts)
    ; Input.mode == "opencv"
    -> Facts = Input.facts, load_facts(Facts), RegionPixels = []
    ; throw(error(domain_error(pipeline, Input.mode), _)) ),
    ( get_dict(w_engine, Input, WEngine) -> true ; WEngine = "crack" ),
    retractall(w_engine_mode(_)),
    assertz(w_engine_mode(WEngine)),
    ( get_dict(strong_edge_pct, Input, SEP0), number(SEP0) -> ActivePct = SEP0 ; ActivePct = 1 ),
    retractall(strong_edge_pct_override(_)),
    assertz(strong_edge_pct_override(ActivePct)),
    ( get_dict(old_strong_edge_pct, Input, OldPct0), number(OldPct0) -> OldPct = OldPct0 ; OldPct = 25 ),
    retractall(crack_angle_tol_override(_)),
    ( get_dict(crack_angle_tol, Input, CAT), number(CAT)
    -> assertz(crack_angle_tol_override(CAT)) ; true ),
    findall(Part, part_json(RegionPixels, Part), Parts),
    findall(B, background(B), RawBackground), sort(RawBackground, Background),
    part_groups(Groups), objects(Objects),
    ( WEngine == "old"
    -> OldGroups = Groups
    ;  retractall(w_engine_mode(_)), assertz(w_engine_mode("old")),
       retractall(strong_edge_pct_override(_)), assertz(strong_edge_pct_override(OldPct)),
       part_groups(OldGroups),
       retractall(w_engine_mode(_)), assertz(w_engine_mode(WEngine)),
       retractall(strong_edge_pct_override(_)), assertz(strong_edge_pct_override(ActivePct))
    ),
    findall(_{id:GroupId, members:Members, area:GroupArea},
            (nth1(GroupIndex, Groups, Members),
             atom_concat(w, GroupIndex, GroupId),
             aggregate_all(sum(Area), (member(Member, Members), region(Member, _, Area, _)), GroupArea)),
            NamedGroups),
    findall([I, O], part_of(I, O), RawContainment), sort(RawContainment, Containment),
    findall([Ch, Par], child_of(Ch, Par), RawChildOf), sort(RawChildOf, ChildOf),
    with_output_to(string(GroupFacts), write_groups_stream(current_output)),
    with_output_to(string(TurtleFacts), write_turtles_stream(current_output)),
    findall(Turtle, turtle_json(Turtle), TurtlePrograms),
    current_prolog_flag(version_data, swi(Major, Minor, Patch, _)),
    format(string(Version), '~w.~w.~w', [Major, Minor, Patch]),
    Output = _{engine:"SWI-Prolog", version:Version, parts:Parts, background:Background,
               groups:Groups, part_groups:NamedGroups, old_groups:OldGroups, objects:Objects, containment:Containment,
               child_of:ChildOf,
               facts:Facts, group_facts:GroupFacts, turtle_facts:TurtleFacts,
               turtle_programs:TurtlePrograms}.

turtle_path(Id, outer, 0, Points, closed) :- polygon(Id, Points).
turtle_path(Id, hole, Index, Points, closed) :-
    region(Id, _, _, _), findall(H, hole(Id, H), Holes), nth1(Index, Holes, Points).
turtle_path(Id, midline, Index, Points, open) :-
    region(Id, _, _, _), findall(M, midline(Id, M), Lines), nth1(Index, Lines, Points).

turtle_json(Turtle) :-
    turtle_path(Id, Kind, Index, Points, Closure),
    region(Id, Color, _, _),
    path_program(Points, Closure, Program),
    maplist(turtle_command_json, Program, Commands),
    Turtle = _{region:Id, kind:Kind, index:Index, color:Color, commands:Commands}.

turtle_command_json(start(X, Y, Heading), _{op:start, x:X, y:Y, heading:Heading}).
turtle_command_json(forward(Distance), _{op:forward, distance:Distance}).
turtle_command_json(turn(Degrees), _{op:turn, degrees:Degrees}).
turtle_command_json(close, _{op:close}).
turtle_command_json(dot, _{op:dot}).

load_facts(Text) :-
    setup_call_cleanup(open_string(Text, Stream), read_facts(Stream), close(Stream)).

read_facts(Stream) :-
    read_term(Stream, Term, [syntax_errors(error)]),
    ( Term == end_of_file -> true
    ; Term = (:- Directive)
    -> (Directive = dynamic(_) ; Directive = discontiguous(_)),
       read_facts(Stream)
    ; ground(Term), functor(Term, Name, Arity), allowed_fact(Name/Arity)
    -> assertz(Term), read_facts(Stream)
    ; throw(error(domain_error(region_fact, Term), _)) ).

allowed_fact(Signature) :-
    memberchk(Signature, [
        region/4, adjacent/2, shared_edge/3, encloses/2, border/1, img_size/2,
        perimeter/2, polygon/2, hole/2, midline/2, fillpoint/3,
        opencv_background_candidate/1, opencv_component/2, opencv_component_area/2,
        opencv_component_centroid/2, opencv_contour/4, opencv_contour_hierarchy/6,
        opencv_morphology/4, opencv_shape_metrics/7, opencv_watershed_count/2,
        opencv_watershed_segment/4, opencv_small_feature/9,
        opencv_small_feature_pixel_run/4, vision_group/4,
        acceptance_parameter/2, foreground_region/3, background_region/1,
        exact_template_candidate/6, symbolic_candidate/4, symbolic_shape_measure/7,
        pixel_shape_measure/5]).

points_json(Points, Json) :-
    findall([X, Y], member(xy(X, Y), Points), Json).

part_json(RegionPixels, Part) :-
    region(Id, Color, Area, centroid(X, Y)),
    findall(Ring, (polygon(Id, Points), points_json(Points, Ring)), Outers),
    findall(Ring, (hole(Id, Points), points_json(Points, Ring)), Holes),
    findall(Line, (midline(Id, Points), points_json(Points, Line)), Midlines),
    findall([FX, FY, Depth], fillpoint(Id, xy(FX, FY), Depth), Peaks),
    findall(Other, adj(Id, Other), Neighbors0), sort(Neighbors0, Neighbors),
    ( memberchk(region(Id, _, Pixels), RegionPixels)
    -> findall([PX, PY], member(PX-PY, Pixels), Cells)
    ; Cells = [] ),
    Part = _{id:Id, color:Color, area:Area, centroid:[X,Y],
             polygons:Outers, holes:Holes, midlines:Midlines, fillpoints:Peaks,
             adjacent:Neighbors, cells:Cells}.

add_pixel_topology(Regions, W, H) :-
    forall((member(region(Id, _, Pixels), Regions), region(Id, _, _, _)),
        ( (member(X-Y, Pixels), (X =:= 0 ; Y =:= 0 ; X =:= W-1 ; Y =:= H-1))
          -> assertz(border(Id))
          ; true )),
    forall((member(region(Id, _, Pixels), Regions), region(Id, _, _, _)),
        ( aggregate_all(count,
              (member(P, Pixels), neighbor4(P, N), \+ ord_memberchk(N, Pixels)), Perimeter),
          assertz(perimeter(Id, Perimeter)) )),
    forall((region(Id, _, _, _), \+ border(Id),
            findall(N, adj(Id, N), Ns0), sort(Ns0, [Outer]), region(Outer, _, _, _)),
           assertz(encloses(Outer, Id))).

emit_extra_topology :-
    forall(border(Id), portray_clause(border(Id))),
    forall(perimeter(Id, P), portray_clause(perimeter(Id, P))),
    forall(encloses(O, I), portray_clause(encloses(O, I))).
