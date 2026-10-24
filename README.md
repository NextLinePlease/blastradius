# BlastRadius

A safety check for software deployments that predicts failure
probability, estimates downstream blast radius, and recommends
a rollout plan for a simulated microservice fleet.

## Scope

All data is simulated. Services, traffic, and faults are generated
by this project's own load generator and chaos injector.
Labels must be derived from injected faults and measured
downstream impact, not randomly assigned.

## Status

Day 1 of 30. Work in progress.