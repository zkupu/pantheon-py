#Project Overview
This is our   project. It does many things.
##Installation
Run `pip install .` to install. Make sure you have python  3.10 or later.You also need to run `pip install -e ".[dev]"` for development.
## usage
To use the project, run `python -m myproject`. You can also use the CLI:
- `myproject run` - runs the thing
-  `myproject test` - tests everything
- `myproject lint`- checks code style
##Configuration
Set these environment variables:
|Variable|Description|Default|
|---|---|---|
|`API_KEY`|Your API key|none|
|`DEBUG`|Enable debug mode|false|
|`PORT`|Server port|8080|

There are no more sections.Here is some code:
```
def hello():
  print("hello")
```
