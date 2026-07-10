# Dynamic MCP Server Framework

## Overview

This project provides a **generic framework for exposing Python modules as MCP tools over HTTP**. It is designed to automatically discover tool modules, execute them safely, and make them available to MCP-compatible clients through a scalable server architecture.

The framework focuses on:

- Automatic tool discovery
- Dynamic module loading
- Safe tool execution
- HTTP-based MCP exposure
- Compatibility with config-driven tools (e.g. Hydra)
- Reusable plugin architecture

---

## Core Architecture

The system is organized into three logical layers:

1. **Server Layer** – Accepts MCP requests and exposes tools over HTTP. Implemented primarily in `expose_mcp_server.py`.
2. **Execution Layer** – Discovers modules, parses payloads, and invokes entrypoints. Implemented primarily in `mcp_entrypoints_utils.py`.
3. **Tool Layer** – Contains user-defined Python modules that implement business logic and are executed by the framework.

---

## Visual Architecture Diagram

```text
MCP Client / Agent
        |
        | Request Tool Call
        v
+----------------------------------+
|          Server Layer            |
|   FastMCP + Starlette + Uvicorn  |
+----------------------------------+
                 |
                 v
+----------------------------------+
|         Execution Layer          |
| Discovery + Payload Parsing      |
| Dynamic Import + Invocation      |
+----------------------------------+
                 |
                 v
+----------------------------------+
|            Tool Layer            |
|   Python Modules / Plugins       |
|     Business Logic Tool          |
+----------------------------------+
```

---

# Code Logic

## 1. Automatic Discovery

At startup, the framework scans the target Python package recursively and identifies modules that can act as tools.

Only modules exposing supported entrypoints are registered. This enables a **zero manual registration** model where adding a new module automatically makes it available after restart.

### Benefits

- Fast onboarding of new tools
- Clean plugin-based design
- Minimal maintenance effort

---

## 2. Dynamic Registration

Each discovered module is converted into an MCP tool and registered with the server runtime.

Tool names are generated automatically from module paths, ensuring a predictable and clean naming convention.

The framework can also use module metadata such as docstrings to provide tool descriptions to clients.

---

## 3. Request Processing Flow

When a client invokes a tool:

1. The HTTP server receives the MCP request.
2. The input payload is validated and normalized.
3. The target module is imported dynamically.
4. The selected entrypoint is executed.
5. The result is returned as structured JSON.

---

## 4. Payload Translation

The framework supports structured JSON inputs and converts them into execution parameters.

This is especially useful for tools originally built for command-line or config-driven workflows.

Examples of supported inputs:

- Arguments lists
- Key/value parameters
- Runtime overrides
- Keyword arguments

This design allows the same tool to be reused across CLI, automation, and MCP environments.

---

## 5. Safe Execution Model

Tool execution is isolated from the async server loop.

Blocking or synchronous tool code runs in worker threads so that the HTTP server remains responsive during long-running operations.

### Benefits

- Supports concurrent requests
- Prevents event loop blocking
- Handles client disconnects correctly
- Improves production reliability

---

## 6. Structured Error Handling

All failures are normalized into machine-readable responses rather than raw crashes.

Typical failure categories include:

- Invalid input payload
- Import errors
- Missing entrypoints
- Runtime exceptions
- Unexpected system exits

This makes the framework easier to integrate with AI agents and external systems.

---

## 7. Configuration Strategy

The framework supports configuration through:

- Environment variables
- Startup CLI arguments
- Runtime payload parameters
- **Hydra configuration files and overrides**

## Hydra Integration

The framework is designed to support tools built with Hydra.

### CONFPATH Resolution

At startup, the server resolves the `CONFPATH` environment variable through `init_confpath()`:

- Supports relative paths
- Expands user paths (e.g. `~`)
- Converts paths to absolute form
- Preserves startup even if the path does not exist

This is especially useful in containers and template-generated projects.

### Runtime Overrides

Incoming tool payload parameters can be translated into Hydra-style CLI overrides such as:

```text
++param=value
```

This allows MCP requests to drive config-based tools dynamically.

### Recommended Entrypoint Pattern

For Hydra tools, use a dedicated `mcp_entrypoint()` that loads configuration with Hydra's functional API (for example `initialize_config_dir()` and `compose()`).

This avoids calling `@hydra.main` directly inside MCP requests, which may terminate the process with `sys.exit()`.

### Benefits

- Reuse existing Hydra tools with minimal changes
- Dynamic configuration per request
- Safe execution inside long-running servers
- Consistent local and remote behavior

This makes deployment flexible across:

- Local development
- Containers
- CI/CD pipelines
- Cloud environments

---

## 8. Extensibility

New tools can be added without changing server code.

Typical extension workflow:

1. Add a new Python module inside the target package.
2. Implement a supported entrypoint.
3. Restart the server.
4. The tool becomes available automatically.

This makes the framework suitable for growing tool ecosystems.

---

# Business Tool

Tool modules are the executable components loaded by the framework. Each tool is responsible for implementing a specific task and exposing a supported entrypoint that the server can invoke.

## Supported Entrypoints

A tool module can expose one of the following callable functions:

- **`mcp_entrypoint()`** – Preferred option for MCP integrations. Allows custom setup and safe execution flows.
- **`main()`** – Standard application entrypoint, often reused from CLI tools.
- **`run()`** – Lightweight generic callable for simple tools.

The framework selects the most appropriate entrypoint automatically.

## Expected Behavior

A business tool should:

1. Receive input parameters directly or through configuration.
2. Execute the intended business logic.
3. Return structured data.
4. Raise or report errors clearly.

## Return Format

Structured responses are recommended, for example:

```json
{
  "status": "ok",
  "data": {}
}
```

or

```json
{
  "status": "error",
  "message": "Description of failure"
}
```

## How to Define a New Tool

To add a new tool to the framework:

1. Create a new Python module inside the target package.
2. Implement one supported entrypoint: `mcp_entrypoint()`, `main()`, or `run()`.
3. Add the business logic inside the module.
4. Accept input parameters directly or through configuration.
5. Return structured JSON or serializable output.
6. Restart the server.
7. The framework will automatically discover and register the new tool.

No manual server registration is required.

---

# Technology Stack

- **FastMCP** – MCP protocol integration and tool registry
- **Starlette** – ASGI web framework
- **Uvicorn** – Production ASGI server
- **Python Importlib** – Dynamic module loading
- **AsyncIO** – Concurrent execution model
- **Hydra (optional)** – Config-driven tool compatibility

---

# Use Cases

This framework is suitable for:

- AI agent tool servers
- Internal automation platforms
- Config-driven Python utilities
- Plugin ecosystems
- Remote execution gateways
- Microservice tool exposure

---

# Final Summary

This project is a **generic MCP server framework** that transforms Python modules into remotely callable tools through automatic discovery, dynamic execution, and scalable HTTP exposure.

It provides a clean foundation for building extensible, production-ready MCP tool platforms.

