:- module(omega_vision,
          [ run_main/2,
            omega_vision_boot/0
          ]).

/** <module> Omega Vision pack loader and entry-point conventions.

    Loading this (library(omega_vision)) registers the `omega_vision` file-search alias so the pack's
    modules can be addressed as `omega_vision/<module>` (the entry-point form), and provides
    `run_main/2` to load-and-run a module's main/1. Install with pack_install/1 on the pack root
    (…/prolog/omega_vision); after install, `use_module(library(omega_vision))` is enough to make the
    `omega_vision/<module>` form and `run_main/2` available.
*/

:- use_module(library(filesex)).

% Register `omega_vision` as a path alias pointing at this pack's module directory
% (…/prolog/omega_vision), so `use_module(omega_vision/web_service)` resolves natively.
:- prolog_load_context(directory, Dir),
   directory_file_path(Dir, 'omega_vision', ModDir),
   ( user:file_search_path(omega_vision, ModDir)
   -> true
   ;  assertz(user:file_search_path(omega_vision, ModDir)) ).

%!  run_main(+Spec, +Args) is det.
%
%   Load module Spec and call its main/1 with Args. Accepts the slash form (omega_vision/learn_movie)
%   or the functional alias form (omega_vision(learn_movie)).
run_main(Spec, Args) :-
    normalize_spec(Spec, FileSpec, Base),
    use_module(FileSpec),
    Goal =.. [main, Args],
    Base:Goal.

% omega_vision/mod  ->  omega_vision(mod) ;  omega_vision(mod) stays ;  bare atom stays.
normalize_spec(Alias/Mod, Norm, Mod) :- !, Norm =.. [Alias, Mod].
normalize_spec(Compound, Compound, Mod) :- compound(Compound), !, arg(1, Compound, Mod).
normalize_spec(Mod, Mod, Mod).

% Let the documented entry-point form `use_module(omega_vision/web_service)` (slash) work by
% rewriting it to the resolvable functional alias form at load/goal-expansion time.
:- multifile user:goal_expansion/2.
user:goal_expansion(use_module(omega_vision/M),    use_module(omega_vision(M))).
user:goal_expansion(use_module(omega_vision/M, L), use_module(omega_vision(M), L)).

%!  omega_vision_boot is det.
%
%   Confirm/create the dedicated Python venv and point the embedded interpreter at it. Call this
%   once before any py_call-based work (the entry modules do this in their main/1).
omega_vision_boot :-
    use_module(omega_vision(venv_boot)),
    venv_boot:ensure_venv.
