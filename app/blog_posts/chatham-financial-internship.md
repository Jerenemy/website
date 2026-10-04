---
title: Building Curve Explorer at Chatham Financial
date: 2026-10-03
summary: Building a unified curve workflow in ONYX Pro with React, TypeScript, C#/.NET APIs, and Vitest during my summer 2026 internship.
---

# Building Curve Explorer at Chatham Financial

From June through August 2026, I worked as a Software Engineer Intern at Chatham Financial in Denver, Colorado. My main project was Curve Explorer within ONYX Pro. I owned and built the feature in React and TypeScript, bringing curve visualization, comparison, and rebuilding into a single workflow.

The project involved more than displaying curve data. It connected a user-facing workflow to backend services and included the testing needed to meet the team's continuous integration requirements. Those three parts—the workflow, the API integration, and the verification—define the work I contributed during the internship.

## Bringing curve workflows together

Curve Explorer consolidated visualization, comparison, and rebuilding, eliminating more than ten manual steps. That consolidation was the central outcome of the feature: activities that required a series of manual actions became part of one workflow within ONYX Pro.

I built the frontend in React and TypeScript. The scope covered the interface for working with curves as well as its connection to the data behind those curves. Describing the project only as a visualization would leave out a substantial part of it. Comparison and rebuilding were also part of the workflow I owned, and bringing all three together was what reduced the manual work.

## Connecting the frontend to curve data

I integrated the frontend with C#/.NET REST APIs to fetch curve data, using Swagger/OpenAPI for the integration. React and TypeScript provided the frontend, while the .NET services supplied the data the feature needed.

The API work was part of building Curve Explorer as a functioning feature within ONYX Pro. The interface and the data integration served the same purpose: supporting the combined curve workflow. Swagger/OpenAPI was the link between the frontend work and the REST API interfaces I used to retrieve that data.

## Testing alongside implementation

I wrote Vitest unit tests covering 90% of the new code. The work met CI requirements for coverage, linting, SonarCloud analysis, and automated tests.

Coverage was one concrete measure of the testing work, alongside the other checks required by the pipeline. The feature therefore included both implementation and verification: building the workflow, integrating the APIs, and writing tests for the new code.

My contribution at Chatham centered on delivering that complete feature. Curve Explorer brought three related activities into one workflow, removed more than ten manual steps, and connected a React and TypeScript frontend to C#/.NET services. Together with the Vitest tests and CI checks, those are the concrete results of my summer internship.
