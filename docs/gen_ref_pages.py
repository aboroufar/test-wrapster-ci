from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

root = Path(__file__).parent.parent
src = root / "src"

# Top-level package name (set at project generation time by Copier)
PACKAGE_NAME = "sf"

for path in sorted(src.rglob("*.py")):
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("reference", doc_path)

    parts = tuple(module_path.parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        full_doc_path = full_doc_path.with_name("index.md")
    elif parts[-1] == "__main__":
        continue

    nav[parts] = doc_path.as_posix()

    # Build content once, reuse for both virtual FS and real disk
    ident = ".".join(parts)
    if parts == (PACKAGE_NAME,):
        content = (
            f"# {PACKAGE_NAME}\n\n"
            f"Reference entrypoint for the public package and its submodules.\n\n"
            "Use the navigation tree to browse module-level API docs; this index page "
            "intentionally avoids rendering package symbols to prevent duplicate reference anchors.\n"
        )
    else:
        content = f"::: {ident}"

    # Write to mkdocs virtual FS (used during the build)
    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        fd.write(content)

    mkdocs_gen_files.set_edit_path(full_doc_path, path.relative_to(root))

# Write SUMMARY.md to virtual FS
with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.write("".join(nav.build_literate_nav()))
