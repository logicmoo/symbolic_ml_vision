:- module(venv_boot,
          [ ensure_venv/0,
            set_omega_vision_root/1,
            project_root/1,
            app_dir/1,
            venv_dir/1,
            venv_site_packages/1
          ]).

/** <module> Self-provisioning Python venv for the swipl-hosted Recognition Studio.

    swipl is the top-level process and embeds Python through library(janus). This module makes
    swipl own the venv end to end: it confirms the dedicated project venv exists, creates it and
    installs requirements when it is missing, then points the embedded interpreter's sys.path at
    that venv so every py_call resolves numpy/scipy/opencv/Pillow/scikit-image and our own
    modules from it. No PYTHONHOME/PYTHONPATH env vars are required.
*/

:- use_module(library(janus)).
:- use_module(library(process)).
:- use_module(library(filesex)).
:- use_module(library(readutil)).

% Capture this module file's directory at load time (…/prolog/omega_vision/prolog/omega_vision).
:- dynamic module_dir_/1, omega_vision_root_/1.
:- prolog_load_context(directory, Dir), retractall(module_dir_(_)), assertz(module_dir_(Dir)).

%!  set_omega_vision_root(+Root) is det.
%   Override the project root (repo dir containing recognition_webapp/, .venv/, data/).
set_omega_vision_root(Root) :-
    retractall(omega_vision_root_(_)),
    assertz(omega_vision_root_(Root)).

% Project root resolution order: explicit override, OMEGA_VISION_ROOT env var, else derived from
% this file's location assuming the in-repo pack layout (…/<root>/prolog/omega_vision/prolog/omega_vision).
project_root(Root) :-
    (   omega_vision_root_(Root0)
    ->  Root = Root0
    ;   getenv('OMEGA_VISION_ROOT', Root0)
    ->  Root = Root0
    ;   module_dir_(ModDir),
        file_directory_name(ModDir, D1),   % …/prolog/omega_vision/prolog
        file_directory_name(D1, D2),       % …/prolog/omega_vision
        file_directory_name(D2, D3),       % …/prolog
        file_directory_name(D3, Root)      % …/<repo root>
    ).

app_dir(App) :-
    project_root(Root),
    directory_file_path(Root, 'recognition_webapp', App).

venv_dir(Venv) :-
    project_root(Root),
    directory_file_path(Root, '.venv', Venv).

venv_site_packages(Site) :-
    venv_dir(Venv),
    ( current_prolog_flag(windows, true)
    -> directory_file_path(Venv, 'Lib/site-packages', Site)
    ;  once(( member(Py, ['python3.13','python3.12','python3.11','python3']),
              directory_file_path(Venv, 'lib', Lib),
              directory_file_path(Lib, Py, PyDir),
              directory_file_path(PyDir, 'site-packages', Site),
              exists_directory(Site) ))
    ).

venv_python(Python) :-
    venv_dir(Venv),
    ( current_prolog_flag(windows, true)
    -> directory_file_path(Venv, 'Scripts/python.exe', Python)
    ;  directory_file_path(Venv, 'bin/python', Python)
    ).

requirements_file(Reqs) :-
    app_dir(App),
    directory_file_path(App, 'requirements.txt', Reqs).

% Base (non-venv) interpreter that hosts the embedded Python; used to build the venv.
base_python(Python) :-
    py_call(sys:base_prefix, Base),
    ( current_prolog_flag(windows, true)
    -> directory_file_path(Base, 'python.exe', Python)
    ;  directory_file_path(Base, 'bin/python3', Python)
    ).

%!  ensure_venv is det.
%
%   Confirm the venv exists (create + install requirements if not), then make the embedded
%   interpreter use it and verify the scientific stack imports.
ensure_venv :-
    venv_dir(Venv),
    ( exists_directory(Venv)
    -> print_message(informational, venv_boot(exists(Venv)))
    ;  print_message(informational, venv_boot(creating(Venv))),
       create_venv,
       install_requirements
    ),
    add_venv_to_path,
    verify_stack.

create_venv :-
    base_python(Base),
    ( exists_file(Base) -> true
    ; throw(error(existence_error(base_python, Base), _)) ),
    venv_dir(Venv),
    run(Base, ['-m', venv, Venv]).

install_requirements :-
    venv_python(Python),
    requirements_file(Reqs),
    ( exists_file(Reqs)
    -> run(Python, ['-m', pip, install, '--upgrade', pip, '--quiet']),
       run(Python, ['-m', pip, install, '-r', Reqs])
    ;  print_message(warning, venv_boot(no_requirements(Reqs)))
    ).

% Run a child process with inherited stdio (live, visible output; no pipe-buffer deadlock on
% long installs) and require a zero exit status.
run(Exe, Args) :-
    print_message(informational, venv_boot(run(Exe, Args))),
    process_create(Exe, Args, [process(PID)]),
    process_wait(PID, Status),
    ( Status == exit(0)
    -> true
    ;  throw(error(process_error(Exe, Status), _)) ).

add_venv_to_path :-
    venv_site_packages(Site),
    ( exists_directory(Site)
    -> py_call(sys:path:insert(0, Site), _),
       app_dir(App),
       py_call(sys:path:insert(0, App), _),
       print_message(informational, venv_boot(on_path(Site)))
    ;  throw(error(existence_error(site_packages, Site), _)) ).

verify_stack :-
    forall(member(Mod, ['numpy', 'scipy', 'PIL', 'cv2', 'skimage']),
           ( catch(py_call(Mod:'__name__', _), E,
                   throw(error(python_import_failed(Mod, E), _)))
           -> print_message(informational, venv_boot(import_ok(Mod)))
           ;  throw(error(python_import_failed(Mod), _)) )),
    py_call(sys:version, V),
    print_message(informational, venv_boot(python_ready(V))).

% Human-readable progress on stderr.
:- multifile prolog:message//1.
prolog:message(venv_boot(exists(V)))        --> ['[venv] confirmed existing venv: ~w'-[V]].
prolog:message(venv_boot(creating(V)))      --> ['[venv] no venv found; creating ~w'-[V]].
prolog:message(venv_boot(run(E, A)))        --> ['[venv] run ~w ~w'-[E, A]].
prolog:message(venv_boot(child_out(S)))     --> ['[venv] ~w'-[S]].
prolog:message(venv_boot(child_err(S)))     --> ['[venv] ~w'-[S]].
prolog:message(venv_boot(on_path(S)))       --> ['[venv] added to sys.path: ~w'-[S]].
prolog:message(venv_boot(import_ok(M)))     --> ['[venv] import ok: ~w'-[M]].
prolog:message(venv_boot(python_ready(V)))  --> ['[venv] embedded Python ready: ~w'-[V]].
prolog:message(venv_boot(no_requirements(R)))--> ['[venv] requirements.txt not found: ~w'-[R]].
