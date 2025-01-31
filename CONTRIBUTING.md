# Contributing to LisztServ

We love your input! We want to make contributing to LisztServ as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## Development Process

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

1. Fork the repo and create your branch from `main`
2. If you've added code that should be tested, add tests
3. If you've changed APIs, update the documentation
4. Ensure the test suite passes
5. Make sure your code lints
6. Issue that pull request!

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/lisztserv.git
   cd lisztserv
   ```

2. Create a virtual environment:
   ```bash
   python -m venv virtual
   source virtual/bin/activate  # or .\virtual\Scripts\activate on Windows
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-test.txt
   ```

4. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Pull Request Process

1. Update the README.md and MASTER_DOCUMENTATION.md with details of changes to the interface
2. Update the requirements.txt if you add any dependencies
3. The PR will be merged once you have the sign-off of at least one maintainer

## Testing

- Run the full test suite before submitting a PR:
  ```bash
  python -m pytest tests/ -v
  ```
- Maintain or improve test coverage
- Add tests for any new functionality

## Code Style

We use several tools to maintain code quality:
- Black for code formatting
- isort for import sorting
- flake8 for style guide enforcement
- mypy for type checking

Run the following before committing:
```bash
black .
isort .
flake8
mypy src/lisztserv
```

## Commit Messages

Format: `type(scope): description`

Types:
- feat: A new feature
- fix: A bug fix
- docs: Documentation only changes
- style: Changes that do not affect the meaning of the code
- refactor: A code change that neither fixes a bug nor adds a feature
- perf: A code change that improves performance
- test: Adding missing tests or correcting existing tests
- chore: Changes to the build process or auxiliary tools

Example:
```
feat(playlist): add support for custom playlist descriptions
```

## License

By contributing, you agree that your contributions will be licensed under its MIT License. 