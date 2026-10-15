---
title: Building Curve Explorer at Chatham Financial
date: 2026-10-03
summary: My summer 2026 internship: one curve workflow in ONYX Pro, built with React, TypeScript, C#/.NET APIs and Vitest.
---

# Building Curve Explorer at Chatham Financial

From June through August 2026 I was a Software Engineer Intern at Chatham Financial in Denver, Colorado. My main project was Curve Explorer, a feature in ONYX Pro that I owned and built in React and TypeScript. It puts curve visualization, comparison and rebuilding in one place.

## One workflow instead of ten steps

Before Curve Explorer, looking at a curve, comparing it with another and rebuilding it were separate jobs with more than ten manual steps between them. Curve Explorer does all three in a single workflow inside ONYX Pro, and getting rid of those steps was the point of the feature.

I wrote the frontend in React and TypeScript. That covered the interface for working with curves and its connection to the curve data underneath.

## Getting the data

The curve data comes from C#/.NET REST APIs. I integrated the frontend with them through their Swagger/OpenAPI definitions.

## Tests and CI

I wrote Vitest unit tests that cover 90% of the new code. The team's CI also checks linting, runs SonarCloud analysis and runs the automated test suite, and the feature passed all of it.
