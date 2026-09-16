:- module(web_service, [main/1, start/1, stop/0]).

/** <module> swipl-hosted HTTP server for Recognition Studio (entry: omega_vision/web_service).

    SWI-Prolog is the top-level process. This module tunes the engine for RAM, self-provisions the
    Python venv (venv_boot), embeds Python via Janus, and serves the whole app with library(http).
    Every request is routed through the shared, host-agnostic Python `web_api.dispatch_request`, so
    the swipl server and the standalone Python http.server host share identical behaviour.

    Launch:
        swipl -g "use_module(library(omega_vision)), run_main(omega_vision/web_service, ['--port','8765'])"
    or after pack_install:
        swipl -g "use_module(omega_vision/web_service), web_service:main(['--port','8765'])"
*/

:- use_module(library(http/thread_httpd)).
:- use_module(library(http/http_dispatch)).
:- use_module(library(http/http_header)).
:- use_module(library(http/http_client)).
:- use_module(library(base64)).
:- use_module(library(janus)).
:- use_module(library(option)).
:- use_module(omega_vision(venv_boot)).

:- dynamic port_/1, data_root_/1.

% Catch-all handler: every path (prefix) is delegated to the shared Python dispatcher.
:- http_handler(root(.), handle, [prefix]).

%!  main(+Args) is det.
%
%   Entry point. Args is a CLI-style list, e.g. ['--port','8765','--data-root','...'].
main(Args) :-
    parse_args(Args, Port, DataRoot),
    start([port(Port), data_root(DataRoot)]),
    print_message(informational, web_service(serving(Port, DataRoot))),
    thread_get_message(_).   % block forever (Ctrl+C to stop)

parse_args(Args, Port, DataRoot) :-
    ( phrase(opts(Opts), Args) -> true ; Opts = [] ),
    ( memberchk(port(P), Opts) -> atom_number(P, Port) ; Port = 8765 ),
    ( memberchk(data_root(DR), Opts)
    -> DataRoot = DR
    ;  default_data_root(DataRoot) ).

opts([port(P)|T])      --> ['--port', P], !, opts(T).
opts([data_root(D)|T]) --> ['--data-root', D], !, opts(T).
opts([_|T])            --> [_], !, opts(T).
opts([])               --> [].

default_data_root(DataRoot) :-
    venv_boot:project_root(Root),
    atomic_list_concat([Root, '/data/omega_vision'], DataRoot).

%!  start(+Options) is det.
%
%   Tune the engine for RAM, boot the venv + embedded Python, and start the HTTP server.
start(Options) :-
    option(port(Port), Options, 8765),
    option(data_root(DataRoot), Options, _),
    ( var(DataRoot) -> default_data_root(DataRoot) ; true ),
    retractall(port_(_)), assertz(port_(Port)),
    retractall(data_root_(_)), assertz(data_root_(DataRoot)),
    tune_engine,
    ensure_venv,                 % confirm/create .venv and put it on the embedded sys.path
    py_call(web_api:'__name__', _),   % import the shared dispatcher once
    http_server(http_dispatch, [port(Port), workers(8)]).

stop :- ( port_(Port) -> http_stop_server(Port, []) ; true ).

% Give the persistent Prolog engine and Python plenty of headroom (full RAM, big tables).
tune_engine :-
    ( current_prolog_flag(bounded, true) -> true ; set_prolog_flag(stack_limit, 8_000_000_000) ),
    catch(set_prolog_flag(table_space, 4_000_000_000), _, true).

%!  handle(+Request) is det.
%
%   Build a plain request dict, hand it to the shared Python dispatcher, and emit the response.
handle(Request) :-
    catch(handle_request(Request), Error,
          ( print_message(error, Error),
            ( catch(message_to_codes(prolog, Error, Codes), _, Codes = "?"),
              string_codes(Msg, Codes),
              format(user_error, '[web_service] HANDLER ERROR: ~w~n', [Msg]) ),
            throw(Error) )).

handle_request(Request) :-
    request_dict(Request, ReqDict),
    py_call(web_api:dispatch_request(ReqDict), Resp),
    emit_response(Resp).

request_dict(Request, ReqDict) :-
    memberchk(method(Method0), Request),
    upcase_atom(Method0, Method),
    memberchk(path(Path), Request),
    ( memberchk(request_uri(URI), Request), sub_atom(URI, _, _, A, '?')
    -> sub_atom(URI, _, A, 0, Query0), atom_string(Query0, Query)
    ;  Query = "" ),
    port_(Port),
    ( memberchk(host(Host0), Request) -> true ; Host0 = '127.0.0.1' ),
    ( sub_atom(Host0, _, _, _, ':') -> Host = Host0 ; format(atom(Host), '~w:~w', [Host0, Port]) ),
    ( memberchk(origin(Origin), Request) -> true ; Origin = @(none) ),
    ( memberchk(content_type(CT), Request) -> content_type_atom(CT, CTAtom) ; CTAtom = '' ),
    ( memberchk(transfer_encoding(TE), Request) -> TEval = TE ; TEval = @(none) ),
    ( Method == 'POST'
    -> read_body(Request, Body)
    ;  Body = "" ),
    data_root_(DataRoot),
    ReqDict = _{ method: Method, path: Path, query: Query, body: Body,
                 host: Host, origin: Origin, port: Port,
                 content_type: CTAtom, transfer_encoding: TEval,
                 data_root: DataRoot }.

% Content-Type header may arrive parsed; normalise to the bare media type (e.g. application/json).
content_type_atom(CT, Atom) :-
    ( atom(CT) ; string(CT) ), !,
    ( sub_atom(CT, Before, _, _, ';') -> sub_atom(CT, 0, Before, _, Bare) ; Bare = CT ),
    normalize_space(atom(Atom), Bare).
content_type_atom(_, '').

read_body(Request, Body) :-
    ( catch(http_read_data(Request, Data, [to(string)]), E,
            ( format(user_error, '[web_service] read_body error: ~w~n', [E]), fail))
    -> ( string(Data) -> Body = Data
       ; atom(Data)   -> atom_string(Data, Body)
       ; term_string(Data, Body) )
    ;  Body = "" ),
    ( Body == "" -> format(user_error, '[web_service] read_body: empty body~n', []) ; true ).

emit_response(Resp) :-
    Status = Resp.status,
    Headers = Resp.headers,
    B64 = Resp.body_b64,
    base64_encoded(PlainString, B64, [encoding(octet), padding(true)]),
    string_codes(PlainString, Bytes),
    dict_pairs(Headers, _, Pairs0),
    % Let SWI's CGI wrapper compute Content-Length; emitting our own duplicates it and breaks
    % keep-alive framing.
    exclude(is_content_length, Pairs0, Pairs),
    stream_property(current_output, encoding(Enc0)),
    setup_call_cleanup(
        true,
        ( format("Status: ~d~n", [Status]),
          forall(member(Name-Value, Pairs), format("~w: ~w~n", [Name, Value])),
          format("~n"),
          set_stream(current_output, encoding(octet)),
          format("~s", [Bytes]) ),
        set_stream(current_output, encoding(Enc0))).

is_content_length(Name-_) :- downcase_atom(Name, 'content-length').

:- multifile prolog:message//1.
prolog:message(web_service(serving(Port, DataRoot))) -->
    ['[web_service] swipl HTTP server on http://127.0.0.1:~w (data-root ~w)'-[Port, DataRoot]].
