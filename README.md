# nicholastacik.github.io

A working notebook — short writeups of things I'm building (often with AI),
stray thoughts, and Kaggle logs. Built with [Quarto](https://quarto.org) and
published to GitHub Pages.

Live at <https://nicholastacik.github.io>.

## New entry

```bash
mkdir -p posts/my-entry
$EDITOR posts/my-entry/index.qmd   # front matter: title, date, categories
git add . && git commit -m "post: my entry" && git push
```

Pushing to `main` triggers the GitHub Action, which renders the site and
publishes it to the `gh-pages` branch.

## Local preview (optional)

Requires Quarto installed (`brew install --cask quarto`):

```bash
quarto preview
```
