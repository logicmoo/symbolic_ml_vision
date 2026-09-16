% Source: logicmoo/omega_vision/prolog/omega_vision/turtle_programs.pl
% Original SHA-256: f46fb851f745196e4a0fdec06860185c114241cb4f168a9e62ccd6a3e981080a
% LGPL-2.1-or-later. Standalone streaming adapter in pipeline_bridge.pl.
% turtle_programs.pl — redraw programs from the parts map, BY PROLOG.
%
% Every per-part list becomes a turtle program EXCEPT fillpoints (fill is a
% bucket operation seeded at a point, not a path to walk):
%
%   polygon(Id, Pts)  -> turtle_program(Id, outer,      Program)   closed
%   hole(Id, Pts)     -> turtle_program(Id, hole(N),    Program)   closed
%   midline(Id, Pts)  -> turtle_program(Id, midline(N), Program)   open
%
% A Program is [start(X, Y, Heading) | Steps] with steps forward(Dist) and
% turn(Deg) (left positive, normalized to (-180,180]), ending in close for
% rings. A degenerate single-point path is [start(X, Y, 0), dot]. Headings
% are degrees in screen coordinates (y grows downward, 0 = +x).
%
% Run: swipl -q -g "consult('turtle_programs.pl'), consult('REGIONS.pl'), write_turtles('turtles.pl')" -t halt

:- dynamic region/4.
:- dynamic polygon/2.
:- dynamic hole/2.
:- dynamic midline/2.
:- dynamic fillpoint/3.

round1(V, R) :- R is round(V * 10) / 10.

heading(X0, Y0, X1, Y1, H) :- H is atan2(Y1 - Y0, X1 - X0) * 180 / pi.

dist(X0, Y0, X1, Y1, D) :- D is sqrt((X1-X0)*(X1-X0) + (Y1-Y0)*(Y1-Y0)).

norm_turn(T0, T) :- T is T0 - 360 * round(T0 / 360).

% walk(+Points, +HeadingIn, -Steps): exact headings carried, emitted values rounded
walk([_], _, []).
walk([xy(X0,Y0), xy(X1,Y1) | Rest], Hin, Steps) :-
    (   X0 =:= X1, Y0 =:= Y1
    ->  walk([xy(X1,Y1) | Rest], Hin, Steps)
    ;   heading(X0, Y0, X1, Y1, H),
        Turn0 is H - Hin, norm_turn(Turn0, Turn),
        dist(X0, Y0, X1, Y1, D0), round1(D0, D),
        walk([xy(X1,Y1) | Rest], H, More),
        (   abs(Turn) < 0.05
        ->  Steps = [forward(D) | More]
        ;   round1(Turn, TR), Steps = [turn(TR), forward(D) | More]
        )
    ).

steps_program([xy(X0,Y0), xy(X1,Y1) | Rest], [start(X0, Y0, HR) | Steps]) :-
    heading(X0, Y0, X1, Y1, H0), round1(H0, HR),
    walk([xy(X0,Y0), xy(X1,Y1) | Rest], H0, Steps).

path_program([xy(X,Y)], _, [start(X, Y, 0), dot]) :- !.
path_program(Points, closed, Program) :- !,
    Points = [First | _],
    append(Points, [First], Ring),
    steps_program(Ring, Body),
    append(Body, [close], Program).
path_program(Points, open, Program) :-
    steps_program(Points, Program).

% ---- machine output ----------------------------------------------------------
write_turtles(File) :-
    setup_call_cleanup(open(File, write, S), write_turtles_stream(S), close(S)).

write_turtles_stream(S) :-
    format(S, "% turtle programs by turtle_programs.pl (prolog doer)~n", []),
    format(S, ":- dynamic turtle_program/3.~n:- discontiguous turtle_program/3.~n", []),
    forall(polygon(Id, Pts),
           ( path_program(Pts, closed, P),
             portray_clause(S, turtle_program(Id, outer, P)) )),
    forall(( region(Id, _, _, _), findall(H, hole(Id, H), Hs), nth1(N, Hs, HP) ),
           ( path_program(HP, closed, P),
             portray_clause(S, turtle_program(Id, hole(N), P)) )),
    forall(( region(Id, _, _, _), findall(M, midline(Id, M), Ms), nth1(N, Ms, MP) ),
           ( path_program(MP, open, P),
             portray_clause(S, turtle_program(Id, midline(N), P)) )).
