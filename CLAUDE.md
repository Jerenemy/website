# Claude instructions for this site

## Writing for the site

Any text written for the website (page copy, blog posts in `app/blog_posts/`, portfolio
descriptions in `app/data/portfolio.seed.json`, meta descriptions, alt text, form and status
messages) goes through the humanizer skill (https://github.com/blader/humanizer) before it
lands. Run `/humanizer` on the draft, or follow its SKILL.md if the slash command is not
installed, and ship only the final rewrite.

Exceptions:

- `app/templates/me_story.html`, the personal story behind /me's "Elsewhere" section. Jeremy
  wrote it himself: never rewrite or "clean up" its text.
- Code, commands, file paths, data and link targets inside the text stay as they are.

## Portfolio data

`app/data/portfolio.json` is the server's live file and is not in git; /admin/portfolio writes
it. Edit `app/data/portfolio.seed.json` instead. After deploying, a change to a work's words
reaches the live site only through `flask --app app portfolio-copy`, run on the server. Order and
publishing are changed in the admin.
