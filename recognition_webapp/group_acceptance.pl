% Recognition-only copy from logicmoo/omega_vision. LGPL-2.1-or-later.
% Original source SHA-256: 98c14c1154eb0abd972a3103fbc3a7879f104e5c4d6fb8db24c6216ad18665ec
% group_acceptance.pl — Prolog-owned final current-frame gN acceptance.
%
% Deterministic measurements are prepared by Python/OpenCV, but only these
% rules accept groups. Order: exact V/W consensus, symbolic analogy (A),
% combined-pixel fallback (C), then singleton foreground remainder (D).

:- dynamic acceptance_parameter/2.
:- dynamic foreground_region/3.
:- dynamic background_region/1.
:- dynamic exact_template_candidate/6.
:- dynamic symbolic_candidate/4.
:- dynamic symbolic_shape_measure/7.
:- dynamic pixel_shape_measure/5.

write_group_acceptance(File) :-
    current_frame_group_acceptance(Records, Rejections, ExactRejections),
    setup_call_cleanup(
        open(File, write, Stream),
        write_acceptance_stream(Stream, Records, Rejections, ExactRejections),
        close(Stream)
    ).

current_frame_group_acceptance(Records, Rejections, ExactRejections) :-
    findall(Order-template(Key, Members, Vs, Ws, Evidence),
            exact_template_candidate(Order, Key, Members, Vs, Ws, Evidence),
            ExactPairs0),
    keysort(ExactPairs0, ExactPairs),
    exact_pass(ExactPairs, [], 1, Trusted, ExactRecords, ExactRejections,
               Covered1, Next1),
    findall(Order-candidate(W, Members, Evidence),
            symbolic_candidate(Order, W, Members, Evidence),
            SymbolicPairs0),
    keysort(SymbolicPairs0, SymbolicPairs),
    symbolic_pass(SymbolicPairs, Trusted, Covered1, Next1,
                  SymbolicRecords, Rejections, Covered2, Next2),
    findall(Order-region(Region, Evidence),
            foreground_region(Order, Region, Evidence),
            ForegroundPairs0),
    keysort(ForegroundPairs0, ForegroundPairs),
    singleton_pass(ForegroundPairs, Covered2, Next2,
                   SingletonRecords, Covered3, _),
    append([ExactRecords, SymbolicRecords, SingletonRecords], Records),
    validate_final_groups(Records, Covered3).

group_atom(Index, Group) :-
    format(atom(Group), 'g~w', [Index]).

members_available([First|Rest], Covered) :-
    foreground_region(_, First, _),
    \+ memberchk(First, Covered),
    forall(member(Member, Rest),
           ( foreground_region(_, Member, _),
             \+ memberchk(Member, Covered) )).

add_covered(Members, Covered0, Covered) :-
    append(Members, Covered0, Combined),
    sort(Combined, Covered).

exact_pass([], Covered, Next, [], [], [], Covered, Next).
exact_pass([Order-template(Key, Members, Vs, Ws, Evidence)|Rest],
           Covered0, Next0, Trusted, Records, Rejections, Covered, Next) :-
    ( members_available(Members, Covered0)
    -> group_atom(Next0, Group),
       Record = accepted(Group, Members, exact_consensus(Vs, Ws), 1.0, Evidence),
       Trusted = [trusted(Key, Group, Order)|TrustedRest],
       Records = [Record|RecordRest],
       Rejections = RejectedRest,
       add_covered(Members, Covered0, Covered1),
       Next1 is Next0 + 1
    ;  Trusted = TrustedRest,
       Records = RecordRest,
       Rejections = [rejected_template(Key, exact_overlap_or_background,
                                       Evidence)|RejectedRest],
       Covered1 = Covered0,
       Next1 = Next0
    ),
    exact_pass(Rest, Covered1, Next1, TrustedRest, RecordRest, RejectedRest,
               Covered, Next).

symbolic_pass([], _, Covered, Next, [], [], Covered, Next).
symbolic_pass([_-candidate(W, Members, _)|Rest], Trusted,
              Covered0, Next0, Records, Rejections, Covered, Next) :-
    ( \+ members_available(Members, Covered0)
    -> Records = RecordRest,
       Rejections = [rejected(W, overlap_or_background)|RejectedRest],
       Covered1 = Covered0,
       Next1 = Next0
    ;  best_symbolic_shape(W, Trusted, TemplateGroup, Score, Evidence)
    -> group_atom(Next0, Group),
       Records = [accepted(Group, Members,
                           symbolic_shape_analogy(W, TemplateGroup),
                           Score, Evidence)|RecordRest],
       Rejections = RejectedRest,
       add_covered(Members, Covered0, Covered1),
       Next1 is Next0 + 1
    ;  best_pixel_shape(W, Trusted, TemplateGroup, Score, Evidence)
    -> group_atom(Next0, Group),
       Records = [accepted(Group, Members,
                           pixel_shape_fallback(W, TemplateGroup),
                           Score, Evidence)|RecordRest],
       Rejections = RejectedRest,
       add_covered(Members, Covered0, Covered1),
       Next1 is Next0 + 1
    ;  pixel_rejection_reason(W, Trusted, Reason),
       Records = RecordRest,
       Rejections = [rejected(W, Reason)|RejectedRest],
       Covered1 = Covered0,
       Next1 = Next0
    ),
    symbolic_pass(Rest, Trusted, Covered1, Next1,
                  RecordRest, RejectedRest, Covered, Next).

best_symbolic_shape(W, Trusted, TemplateGroup, Score, Evidence) :-
    acceptance_parameter(symbolic_geometry_tolerance, Tolerance),
    findall(key(NegativeScore, TemplateOrder)-match(TemplateGroup0, Score0, Evidence0),
            ( symbolic_shape_measure(W, TemplateKey, true, true,
                                     GeometryError, Score0, Evidence0),
              GeometryError =< Tolerance,
              memberchk(trusted(TemplateKey, TemplateGroup0, TemplateOrder), Trusted),
              NegativeScore is -Score0
            ),
            Matches),
    keysort(Matches, [_-match(TemplateGroup, Score, Evidence)|_]).

best_pixel_shape(W, Trusted, TemplateGroup, Score, Evidence) :-
    acceptance_parameter(pixel_shape_threshold, Threshold),
    acceptance_parameter(pixel_unique_margin, Margin),
    acceptance_parameter(pixel_color_mass_tolerance, ColorTolerance),
    findall(key(NegativeScore, TemplateOrder)-match(TemplateGroup0, Score0, Evidence0),
            ( pixel_shape_measure(W, TemplateKey, Score0, ColorError, Evidence0),
              Score0 >= Threshold,
              ColorError =< ColorTolerance,
              memberchk(trusted(TemplateKey, TemplateGroup0, TemplateOrder), Trusted),
              NegativeScore is -Score0
            ),
            Matches0),
    keysort(Matches0, Matches),
    unique_best_pixel(Matches, Margin, TemplateGroup, Score, Evidence).

unique_best_pixel([_-match(TemplateGroup, Score, Evidence)], _,
                  TemplateGroup, Score, Evidence).
unique_best_pixel([_-match(TemplateGroup, Score, Evidence),
                   _-match(_, RunnerUpScore, _)|_],
                  Margin, TemplateGroup, Score, Evidence) :-
    Score - RunnerUpScore >= Margin.

pixel_rejection_reason(_, [], no_trusted_template) :- !.
pixel_rejection_reason(W, Trusted, no_trusted_template) :-
    \+ ( pixel_shape_measure(W, TemplateKey, _, _, _),
         memberchk(trusted(TemplateKey, _, _), Trusted) ),
    !.
pixel_rejection_reason(W, Trusted, ambiguous) :-
    acceptance_parameter(pixel_shape_threshold, Threshold),
    acceptance_parameter(pixel_unique_margin, Margin),
    acceptance_parameter(pixel_color_mass_tolerance, ColorTolerance),
    findall(key(NegativeScore, TemplateOrder)-Score,
            ( pixel_shape_measure(W, TemplateKey, Score, ColorError, _),
              Score >= Threshold,
              ColorError =< ColorTolerance,
              memberchk(trusted(TemplateKey, _, TemplateOrder), Trusted),
              NegativeScore is -Score
            ),
            Matches0),
    keysort(Matches0, [_-Best, _-RunnerUp|_]),
    Best - RunnerUp < Margin,
    !.
pixel_rejection_reason(_, _, below_threshold).

singleton_pass([], Covered, Next, [], Covered, Next).
singleton_pass([_-region(Region, Evidence)|Rest], Covered0, Next0,
               Records, Covered, Next) :-
    ( memberchk(Region, Covered0)
    -> Records = RecordRest,
       Covered1 = Covered0,
       Next1 = Next0
    ;  group_atom(Next0, Group),
       Records = [accepted(Group, [Region], singleton_remainder(Region),
                           1.0, Evidence)|RecordRest],
       add_covered([Region], Covered0, Covered1),
       Next1 is Next0 + 1
    ),
    singleton_pass(Rest, Covered1, Next1, RecordRest, Covered, Next).

validate_final_groups(Records, Covered) :-
    findall(Region, foreground_region(_, Region, _), Foreground0),
    sort(Foreground0, Foreground),
    sort(Covered, Foreground),
    findall(Member,
            ( member(accepted(_, Members, _, _, _), Records),
              member(Member, Members) ),
            Flat),
    sort(Flat, Unique),
    length(Flat, Count),
    length(Unique, Count),
    \+ (member(Background, Flat), background_region(Background)).

write_acceptance_stream(Stream, Records, Rejections, ExactRejections) :-
    format(Stream, '% final current-frame groups by SWI-Prolog group_acceptance.pl~n', []),
    forall(member(Name/Arity,
                  [accepted_group/2, group_acceptance/3,
                   group_acceptance_evidence/2, group_rejection/2,
                   template_rejection/3]),
           ( format(Stream, ':- dynamic ~w/~w.~n', [Name, Arity]),
             format(Stream, ':- discontiguous ~w/~w.~n', [Name, Arity]) )),
    forall(member(accepted(Group, Members, Mode, Score, Evidence), Records),
           ( format(Stream, 'accepted_group(~w, ~q).~n', [Group, Members]),
             format(Stream, 'group_acceptance(~w, ~q, score(~9f)).~n',
                    [Group, Mode, Score]),
             format(Stream, 'group_acceptance_evidence(~w, ~q).~n',
                    [Group, Evidence]) )),
    forall(member(rejected(W, Reason), Rejections),
           format(Stream, 'group_rejection(~w, ~w).~n', [W, Reason])),
    forall(member(rejected_template(Key, Reason, Evidence), ExactRejections),
           format(Stream, 'template_rejection(~w, ~w, ~q).~n',
                  [Key, Reason, Evidence])).
