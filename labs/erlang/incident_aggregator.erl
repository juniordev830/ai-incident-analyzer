-module(incident_aggregator).
-export([summarize/2]).
-include_lib("eunit/include/eunit.hrl").

%% Strict, deterministic incident-window aggregation.
-spec summarize([number()], number()) -> map().
summarize(Measurements, Threshold) when is_list(Measurements),
                                          is_number(Threshold), Threshold > 0 ->
    case lists:all(fun(X) -> is_number(X) andalso X >= 0 end, Measurements) of
        false -> erlang:error(badarg);
        true ->
            #{count => length(Measurements),
              breaches => length([X || X <- Measurements, X > Threshold]),
              maximum => lists:foldl(fun erlang:max/2, 0, Measurements)}
    end;
summarize(_, _) -> erlang:error(badarg).

summarize_test() ->
    ?assertEqual(#{count => 3, breaches => 1, maximum => 400},
                 summarize([20, 100, 400], 100)),
    ?assertEqual(#{count => 0, breaches => 0, maximum => 0},
                 summarize([], 100)),
    ?assertError(badarg, summarize([-1], 100)),
    ?assertError(badarg, summarize([1], 0)).
