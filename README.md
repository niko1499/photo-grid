
# PhotoGrid

A photo website for GitHub Pages. Drop photos into folders, push, and the site updates itself.

- **Photos** tab: every photo as a square tile. Click one to open it full size.
- **Albums** tab: one album per folder, with a cover, photo count and date.
- **View controls** next to the tabs: switch between a square grid and each photo's real proportions, and zoom the grid from 50% to 200%.
- Lightweight, Dark, edge-to-edge mosaic in the style of the HTML5 UP "Multiverse" theme.


# requirements
Python
https://www.python.org/downloads/
Pillow>=10.0
```pip install pillow```
https://pypi.org/project/pillow/

## Viewing photos

- The two icons next to the tabs switch between a **square grid** and each photo's **original proportions** (landscape photos are shown twice as wide as a portrait, packed edge to edge with no gaps between pictures).
- The slider to their left **zooms** the grid, from 50% to 200%, defaulting to 100% and snapping back to it when you're within 10%. You can also zoom with **Ctrl +/-**, or **Ctrl and the scroll wheel** while the cursor is over the photos (not over this bar).


## Publish it

1. Put this folder in a GitHub repository and push it to the `main` branch. (If your default branch is `master`, change `branches: [main]` in `.github/workflows/pages.yml`.)
2. In the repository go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**. You only do this once.
3. Edit `site.json` (title, bio, links), add photos to `photos/`, and push.

The workflow in `.github/workflows/pages.yml` builds the site and deploys it. Your address will be `https://<user>.github.io/<repo>/`. Progress shows under the **Actions** tab.

## Adding photos

One folder per album. The folder name is the album name.

```
photos/
  2024-07 Iceland/         album "Iceland", dated July 2024
    DSC_0001.jpg
    Golden hour.jpg        a caption, because the file has a real name
    cover.jpg              used as the album cover
  Tokyo/
  road-trip/               album "Road Trip"
  loose-photo.jpg          appears in Photos but in no album
  _drafts/                 ignored (anything starting with _ or .)
```

| You do | You get |
| --- | --- |
| Put photos in `photos/<Name>/` | An album called `<Name>` |
| Start a folder name with `2024`, `2024-07` or `2024-07-14` | That album date, removed from the title |
| Use no date in the folder name | The date of the earliest photo (from its EXIF data) |
| Name a file `Golden hour.jpg` | The caption "Golden hour" in the viewer |
| Keep camera names like `IMG_0234.jpg` | No caption |
| Name a file `cover.jpg` | That photo as the album cover (otherwise the first photo) |
| Put a folder inside a folder | A separate album named after the inner folder |
| Delete a photo or folder | It disappears from the site on the next push |

Supported: JPG, PNG, WebP, TIFF. iPhone HEIC files need converting to JPG first.

Photos in an album are ordered by file name (`01-`, `02-` prefixes work). Albums are ordered newest first, with undated albums after.

## Settings (`site.json`)

| Key | Meaning |
| --- | --- |
| `title`, `subtitle` | Header text. The title is bold, the subtitle is light. Also used for the browser tab. |
| `description` | Text search engines show under your site name |
| `author`, `bio`, `email`, `links` | Shown in the About panel. Leave `bio`, `email` and `links` empty and the About button disappears. Separate bio paragraphs with a blank line (`\n\n`). |
| `sort` | Order of the Photos tab: `newest` (by the date stored in each photo), `oldest`, `name`, or `random` (reshuffled on every build). A photo with no date of its own is placed as if taken at the start of its album's date (the date in the folder name, or else the earliest photo in the album). Undated photos in an undated album, or in no album, come last. |
| `exif_fields` | What the viewer shows and in what order. Choose from `camera`, `lens`, `focal`, `aperture`, `shutter`, `iso`, `date`. Use `[]` to show nothing. |
| `thumb_size` | Thumbnail width and height in pixels (default 480) |
| `large_size` | Longest edge of the full-size copy in pixels (default 2200) |
| `quality` | WebP quality, 1 to 100 (default 80) |

If you change `thumb_size`, `large_size` or `quality`, the next build regenerates every image automatically.

## Preview on your computer

You need Python 3.9 or newer.

```
pip install -r requirements.txt
python build.py
python -m http.server -d _site
```

Then open http://localhost:8000. Opening `_site/index.html` by double-clicking doesn't work, because browsers block a page from reading its own data file. The page tells you this if you try.

Rebuilds are fast: only new or changed photos are processed. Use `python build.py --clean` to rebuild everything.

## How it works

```
photos/  ──►  build.py  ──►  _site/  ──►  GitHub Pages
                 │            ├─ index.html, style.css, app.js   (from web/)
                 │            ├─ data.json   (albums, photos, EXIF, your settings)
                 │            └─ img/thumb/, img/large/   (WebP)
                 └─ the only dependency is Pillow
```

- `build.py` finds every image, turns folders into albums, writes the two image sizes and `data.json`. GPS location and other metadata are **not** copied into the published images or `data.json`.
- `web/app.js` fetches `data.json` and draws the page. Views use the URL hash (`#/albums/iceland`), so it works under any repository path with no server setup.
- The originals stay in your repository only. Visitors download the web-sized copies.

### Project layout

```
photos/                  your photos (one folder per album)
site.json                your settings
build.py                 the build script
requirements.txt         Pillow
web/index.html           page shell
web/style.css            theme; colours and sizes are variables at the top
web/app.js               tabs, view modes, zoom, mosaic, albums, viewer, About panel
.github/workflows/       automatic deploy
```

## Planned Features

- **Allow linking to externally served photos such as Immich or Google Photos to get around git around repo size limits**
- **Link straight to a photo:** the viewer already knows which photo is open; add it to the URL hash in `openViewer()`.
- **Search or tags:** filter `data.photos` in `photosView()`.
- **Sort by date assending/decending**

## Tips

- GitHub recommends keeping a repository under about 1 GB. If your originals are large, resize them to around 3000 px on the long edge before adding them. The site only uses 2200 px anyway.
- A bad or corrupt image is skipped with a warning in the build log rather than stopping the deploy.
- Deploys can take a minute or two. `data.json` is cached by browsers for up to ten minutes, so a very recent change can take a moment to appear for returning visitors.

## Credits

- The look is inspired by [Multiverse](https://html5up.net/multiverse), as used in [rampatra/photography](https://github.com/rampatra/photography). 
- The Albums idea comes from [sunbliss/photorama](https://github.com/sunbliss/photorama). 

All code here is new and none of it is copied from either project.

## License
- Source code is under MIT license. Credit links and/or forks of repo are requested and appreciated. (See LICENSE.txt)
- Images are the creative works of Nikolas Gamarra distribution of the images without credit or for comercial purposes is not permitted (See LICENSE.txt)




