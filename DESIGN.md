# Traverse

## Technicals

Traverse is a web app written in python / fastapi and htmx to demonstrate the power of simple python apps for complicated tasks. Traverse allows the user to explore points of interest for a given location and "traversal method". So for example, if I say start from KSVR with a cessna 172, the search for things to do should look up airports and intersting points of interest at each one perhaps for a pilot. Conversely, if I type in Ikebukoro, Tokyo, Japan + transit (train+bus) then I should get some options for a quick trip of sights to see accessible within these places.

## Goals

* Leverage duckdb for initial database
* Leverage python tools such as datatools and fastapi to build a beautiful demonstration of api integration + geo ref for a practical use case
* Something simple to demo to a python-based meetup

## References

* ~/dev/f/floatslope -> a trip navigation finder, a bit more complicated, but has a working scaffold

