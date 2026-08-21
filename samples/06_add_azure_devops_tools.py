"""Run the production Azure DevOps review CLI.

The reusable tool definitions live in ``pr_reviewer.ado_tools``. See that module when
learning how custom Copilot tools are defined and registered.
"""

from pr_reviewer.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
