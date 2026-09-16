:- module(learn_movie, [main/1, crawl/1]).

/** <module> swipl crawler entry (omega_vision/learn_movie).

    Walks every recording and runs the shared Python frame_pipeline (recognition -> cross-frame
    deduction -> .pl/.metta/.json per frame -> inductive guesses) via Janus, hosted in the persistent
    swipl process. Reuses the exact same pass the standalone Python crawler runs
    (crawler.crawl_once), so no logic is forked. Maintains the source.stamp / produced.jsonl control
    files and re-execs a fresher swipl when the source changes; sleeps 10s when idle.

    Launch:
        swipl -g "use_module(library(omega_vision)), run_main(omega_vision/learn_movie, [])"
    Options: --once (single pass), --pipeline prolog|opencv, --data-root DIR.
*/

:- use_module(library(janus)).
:- use_module(library(option)).
:- use_module(library(process)).
:- use_module(omega_vision(venv_boot)).

main(Args) :-
    ensure_venv,                              % confirm/create .venv, embed Python
    py_call('crawler':'__name__', _),         % import the shared crawler module
    parse_args(Args, Pipeline, DataRoot, Once),
    py_call(frame_pipeline:source_epoch(), Launched),
    py_call(crawler:write_stamp(DataRoot, Launched), _),
    format(user_error, '[learn_movie] data-root ~w; pipeline ~w; source stamp ~0f~n',
           [DataRoot, Pipeline, Launched]),
    crawl(_{data_root: DataRoot, pipeline: Pipeline, once: Once, launched: Launched}).

parse_args(Args, Pipeline, DataRoot, Once) :-
    ( memberchk('--once', Args) -> Once = true ; Once = false ),
    ( nth0(I, Args, '--pipeline'), I1 is I+1, nth0(I1, Args, P) -> Pipeline = P ; Pipeline = prolog ),
    ( nth0(J, Args, '--data-root'), J1 is J+1, nth0(J1, Args, D) -> DataRoot = D
    ; default_data_root(DataRoot) ).

default_data_root(DataRoot) :-
    venv_boot:project_root(Root),
    atomic_list_concat([Root, '/data/omega_vision'], DataRoot).

%!  crawl(+State) is det.
crawl(State) :-
    Launched = State.launched,
    ( source_newer(Launched) -> reexec(State) ; true ),
    py_call(crawler:crawl_once(State.data_root, State.pipeline, Launched), DidWork),
    ( State.once == true
    -> true
    ;  ( truthy(DidWork)
       -> crawl(State)                        % more may have changed; pass again
       ;  format(user_error, '[learn_movie] idle; watching source stamp every 10s.~n', []),
          wait_for_source(Launched),
          reexec(State) )
    ).

truthy(true).
truthy(@(true)).

source_newer(Launched) :-
    py_call(frame_pipeline:source_epoch(), Now),
    Now > Launched.

wait_for_source(Launched) :-
    ( source_newer(Launched) -> true ; sleep(10), wait_for_source(Launched) ).

% Re-launch a fresher swipl (picks up updated source), preserving the same entry, then exit.
reexec(_State) :-
    format(user_error, '[learn_movie] source changed; re-launching a fresher swipl crawler.~n', []),
    current_prolog_flag(os_argv, [Exe|_]),
    Goal = 'use_module(library(omega_vision)), run_main(omega_vision/learn_movie, [])',
    catch(process_create(Exe, ['-g', Goal], [detached(true)]), _, true),
    halt(0).
