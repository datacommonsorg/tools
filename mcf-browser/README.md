# Local MCF Browser

This web application overlays data from local MCF or TMCF+CSV files onto the Data Commons Knowledge Graph (DC KG) in order to preview the data without needing access to write to the graph.

Try it out now: https://datacommonsorg.github.io/tools/mcf-browser/

### Features
  - Directly upload MCF files or pairs of TMCF+CSV files or specify URL(s) for the file(s).
  - Navigate the nodes from the local file data and the Data Commons KG.
  - Search by local or dcid IDs.
  - Color coding indicates if a node exists in the Data Commons KG and alerts user of potential errors.

### How to Use
  - Directly upload files via file selector by using the upload buttons.
  - And/or specify a file by inputting its url in the provided spaces.
  - There can be many files uploaded at one time to see how local data will interact with itself in the Data Commons KG along with the remote data.
  - It is possible to upload multiple MCF files at one time via the file selector, but only one MCF file can be uploaded at a time via URL.
  - Only select/specify a single pair of TMCF+CSV files per upload. Multiple pairs of files can be loaded at one time.
  - After specifying file(s) by URL(s), press \<Enter\> to submit the URL(s).
  - Once files are loaded, click a displayed node to view it or use the search bar to search for a local id or dcid (include the namespace 'l' if you are looking for a local id)
  - Once viewing a single node, click other nodes to navigate the graph or return Home to see the list of subject nodes again.

### Design

The files responsible for this application are split into two sections: front-end and back-end. The front-end files, found in `/src/`, use React to implement the user interface. The back-end files, found in `/src/back-end`, serve as the functional implementation of the tool by creating a local version of the Data Commons KG within the browser and incorporates the local data parsed from the passed in files.

##### Back-end

The back-end parses local files to model the Knowledge Graph by creating Node and Assertion objects. TMCF+CSV files are first translated to MCF formatting. MCF files are parsed line by line to create the local version of the KG. When encountering a line beginning with 'Node:', the parser will create a new Node which will be the subject of all following assertions (triples) until a new line beginning with 'Node:' is reached. When parsing property lines of the MCF, the target entity is checked to see if it is another entity (indicated by a namespace) or a text based value. If it is another entity, then a new Node object is created for that entity and stored as the target of that Assertion. Additionally, an inverse assertion is created between the source and the target which is useful when displaying the graph data.

Note: Each Node objects have both 'localId' and 'dcid' properties, although one or the other may not contain values. When searching for a Node within the nodeHash, a namespace must be provided as part of the given id to search for.

When nodes are retrieved from the local version of the KG, it is checked to see if the node has a specified dcid. If it does, then it is verified if the dcid exists in the Data Commons KG. Additionally, triples from the DC KG regarding that node are loaded into local memory and also displayed to the user. This is how the local data is overlaid with the local data.

Brief description of each file:
  - graph.js - Contains the implementation of the Node and Assertion classes. Each node represents a single entity within the Data Commons KG and each Assertion represents a triple by storing a source (Node), property(Text), and target(Node or Text).
  - parse-mcf.js - Implements the ParseMcf class which parses an MCF file and creates a local Knowledge Graph using the Node and Assertion classes.
  - parse-tmcf.js - Implements the ParseTmcf class which creates a template string from one TMCF file and fills in the template based on each row of a given CSV file to create an MCF String.
  - utils.js - Contains various helper functions, including those used to query the Data Commons KG.
  - server-api.js - Acts as a wrapper for the functions needed by the front-end so that only this file is imported into the front-end files.

##### Front-end

The front-end of this application has been implemented with React. The application's main state is saved in the App component. This stores the files which have already been loaded in, which node (if any) should be currently displayed, and more. The App component renders the Header component, which gives the user the option to return to the home page or search for a specific Id.

If there is a node that needs to be displayed, then the App component will render the DisplayNode component. This component fetches all of the relevant triples from the back-end and passes them to TriplesTable components (one table for outgoing triples and one for incoming). The TriplesTable component renders the list of triples in a table so that one row of the table corresponds to a single triple.

If there is no node to be displayed, the the App component renders the Home component. If no files have been loaded to the application, the the Home component will solely display the FileEntry component to prompt the use to upload files. Once files have been uploaded, the Home component displays lists of the loaded files and the subject nodes of each triple within the file(s). The Home component will also display the ParsingErrorsTable component which displays any errors that were encountered in parsing the files. The Home component also has a button which allows the user to reveal a collapsible FileEntry component if they would like to add more files to their KG.

Brief description of each JSX file:
  - App.jsx - Maintains the overall state of the application, including loaded files and which node should be displayed. Renders the Header component followed by DisplayNode if a node has been selected by the user and Home otherwise.
  - Header.jsx - Displays the header containing the 'Return Home' button and search bar.
  - Home.jsx - If no files have been indicated by user, displays file entry options. Otherwise, displays the currently loaded files and their subject nodes.
  - DisplayNode.jsx - Retrieves data for a given dcid from the back-end and displays the triples associated with the node via TriplesTable components.
  - TriplesTable.jsx - Renders a table where each row represents a triple from a given list of Assertions.
  - FileEntry.jsx - Renders the options for how a user can upload files or specify the URL(s) for them.
  - ParsingErrorsTable.jsx - Renders the errors found in parsing into a table format.
  - LoadingSpinner.jsx - Simple component with spinning animation to indicate when a page is loading.
  - utils.js - Contains helper functions to set the window's hash and various parameters in the url of the application.

### Deploying Modifications

This application is currently deployed via GitHub Pages which hosts the application's entry point, `index.html`, at https://datacommonsorg.github.io/tools/mcf-browser/. This uses the files in `static/` which are auto-generated using React scripts from the files in `src/`. The typical work flow for making changes to this tool is:

1. Modify files within `src/`.
2. *Deploy locally from source files* to test the application based on the modifications.
3. *Create deployable build from source files* when satisfied with the modifications and current status of the application.
4. *Deploy locally from build files* to ensure the build version of the application is up to date and the application is running smoothly.
5. Create a Pull Request for the changes in `src/` **AND** the build files (ex: `index.html` and `static/`) Changes in files from `src/` will not be reflected within the tool, only changes in the build files are expressed in the published tool.

**Note** that the application does not actively run the files in `src/`. Those files are converted to the files in `static/` by building the deployable application using React scripts. To create a deployable version of the application after modifying files in `src/`, follow the instructions in *Create deployable build from source files*.

#### Install node.js and npm
To run and test locally, you will need node.js and npm installed. If you do not have these, visit [node.js website](https://nodejs.org/en/download/) to download and install node.js, then install npm.

You can run the following commands to ensure you have both node.js and npm installed:
```sh
$ node -v
$ npm -v
```

#### Install node modules
After forking this repo, ensure you are in `/tools/mcf-browser/`,
then run:
```sh
$ npm install
```
which will install the packages specified in `package.json`.

#### Deploy locally from source files

Launch a local version of the application based on the files from 'src/` with:
```sh
$ npm start
```
This is used when developing the application to get real time feedback for how changes in source files affect the UI and overall application. Once the application is in its desired state, create a deployable build from the source files.

#### Create deployable build from source files
The .js and .jsx files in `src/` are converted to their static format by running:
```sh
$ npm run build
```
The deployable build files will be written to a new directory, `build/`. This new directory includes `index.html` (the entry point of the application) and the sub-directory `build/static/` which contains the compiled versions of the files from `src/` which `index.html` refers to.  These files must be moved to `/tools/mcf-browser/` by running:
```sh
$ cp -r build/* .
$ rm -r build
```
from the `/tools/mcf-browser/` directory. This ensures that `index.html` is hosted at https://datacommonsorg.github.io/tools/mcf-browser/ and not `https://datacommonsorg.github.io/tools/mcf-browser/build/`.


#### Deploy locally from build files
To run and test the front-end from the build files, simply open `index.html`.

For example, in the Chromebook's command line the html file be opened with:

```sh
$ google-chrome index.html
```

This is useful for ensuring that `npm run build` was successful in creating the build that was intended. This is what https://datacommonsorg.github.io/tools/mcf-browser/ will be hosting so it is important to ensure this version of the build is what is intended to become published as an update to the tool.  

#### Testing

After installing node_modules, tests for the back-end found in `src/back-end/test/` can be run with:
```sh
$ npm run test
```

### Future Considerations
Because this tool is hosted via GitHub Pages, the entire `/tools` repo is being published. It may be better to host this tool via App Engine in the future or a different platform to avoid publishing the entire `/tools` repo.
