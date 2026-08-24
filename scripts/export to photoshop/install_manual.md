# Export to Photoshop script

## Installation

There are 2 ways to install.

1. Simply open the jsx file via `File -> Scripts -> Open... ` and select the script manually. The downside is that doing this every time is not convenient.
2. Place the jsx file in `Disk:\Program Files\Adobe\Adobe Photoshop [Version]\Presets\Scripts`. The script will be displayed in the `File -> Scripts` interface.

## Usage

1. Run the script from `File -> Scripts`.
2. Select your project's JSON file.
3. From the proposed list, select your image that is open in Photoshop.
4. In the window that opens, choose the import options you need.
5. The script will create text blocks from the project data.

### Explanation of settings

**Import original and translation** - import the original and translation blocks, respectively. Import works either separately or together; 2 versions of blocks are created.

**Hide original and hide translation** - if you need the blocks to be hidden after import (for example, if you selected both import options, then these checkboxes will hide the visibility of the blocks in the layers panel)

**Use block text** - use block closed and block open. They differ in how the text is wrapped inside the text block region.

## Known limitations

- The font is not imported.
- Text effects such as Italic, Bold and Underline are not imported.
- Some character settings available in the app are not available in import.
- Large JSON files may take noticeable time to read and process.
