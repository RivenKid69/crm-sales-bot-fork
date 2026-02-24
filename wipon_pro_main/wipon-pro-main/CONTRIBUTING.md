# Contribution rules for Agents Panel

## Commits style requirements

- Commits naming should follow rules - [https://www.conventionalcommits.org/en/v1.0.0/](https://www.conventionalcommits.org/en/v1.0.0/)
- Commits naming should use present tense ("add feature" not "added feature")
- Commits naming should use imperative mood ("move cursor to..." not "moves cursor to...")

## Examples of good commit names

`init` - used to initialize project or task

```
init: initialize project
init: set up charts dependencies
```

`feat` - used to identify implement functionality (added footer markup, created product card component)

```
feat: implement product card component
feat: create markup of footer
```

`fix` - fix problem of previously implement functionality

```
fix: change loading indicator display condition
fix: adjust social links to mobile width
```

`refactor` - no new functionality is added but code is made better

```
refactor: format main layout file
refactor: put components into separate folder
```

`docs` - used to identify changes related to project documentation (markdown files, swagger documentation)

```
docs: document devices create endpoint
docs: add examples of API responses for users create endpoint
```

## Git flow and branching

There are 4 types of branches deduced from main branches (master, dev)

`feature/<feature-name>` - implementation of new feature

`fix/<fix-name>` - fix of the existing feature

`docs/<documenting-functionality-name>` - working with documentation

`refactor/<refactoring-functionality-name>` - refactor existing code base
