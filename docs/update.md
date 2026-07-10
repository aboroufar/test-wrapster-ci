# Updating a project

Copier has an "update" feature.
It means that, once a project is generated,
you can keep updating it with the latest changes
that happen in the template.

It's particularly useful when you manage a lot of projects,
all generated from the same template, and you want to
apply a change to all your projects.

Example: the template fixed a bug in the pyproject.toml.
You don't want to apply it manually to your projects.

To update your project, go into its directory,
and run `copier update`. Your repository must be clean
(no modified files) when running this command.

Copier will use the previous answers you gave when
generating the project, to re-generate it in a temporary
directory, compare the two versions, and apply patches
to your documents. When it's not sure, or when there's
a conflict, it will ask you if you want to skip that
change or force it. Your previous answers are stored
in the `.copier-answers.yaml` file at the root
of the project directory:

```
📁 my-project
├── 📄 .copier-answers.yaml
└── 📄 etc.
```

And the file looks like this:

```yaml
# Changes here will be overwritten by Copier.
_commit: v0.162-19-g0c10040
_src_path: gitlab@git.bskyb.com:service-team/tools/wrapster-project-template.git
author_email: amir.boroufar@sky.com
author_fullname: Amir boroufar
author_username: abcd
copyright_holder: Amir boroufar
keywords: api, wrapper
license: ISC
package_name: test_package
project_name: test-project
project_short_description: provide a wrapper, documentation and DevOps best practices
python_version: py312
repository_name: test-project
repository_namespace: git.sky.com
repository_provider: gitlab.com
ssh_private_key: ~/.ssh/id_ed25519
version: 0.1.0
```

If you want to use all previous answers
without copier prompting you for each answer,
run `copier update --force`.

Since we are generally using Git in our projects,
my recommendation is to not think at all
and blindly apply every change Copier proposes.
Indeed, you'll be able to see the diff with `git diff`,
un-apply changes on whole files with `git checkout -- FILE`
if they are not relevant,
or do partial, interactive commits with `git add -p`
or within your IDE interface
(PyCharm and VSCode have good support and UX
for selecting and committing changes).
