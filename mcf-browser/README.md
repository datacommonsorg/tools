# Local MCF Browser

This web application overlays data from local MCF or TMCF+CSV files onto the Data Commons Knowledge Graph (DC KG) in order to preview the data without needing access to write to the graph.

Try it out now: https://datacommonsorg.github.io/tools/mcf-browser/

### Features
  - Directly upload one MCF file or one pair of TMCF+CSV files or specify URL(s) for the file(s).
  - Navigate the nodes from the local file data and the Data Commons KG.
  - Search by local or dcid IDs.
  - Color coding indicates if a node exists in the Data Commons KG and alerts user of potential errors.

### How to Use
  - Directly upload files via file selector by using the upload buttons.
  - And/or specify a file by inputting its url in the provided spaces.
  - There can be many files uploaded at one time to see how local data will interact with itself in the Data Commons KG along with the remote data.
  - It is possible to upload multiple MCF files at one time via the file selector, but only one mcf can be uploaded at a time via URL.
  - Only select/specify a single pair of TMCF+CSV files per upload. Multiple pairs of files can be loaded at one time.
  - Once files are loaded, click a displayed node to view it or use the search bar to search for a local id or dcid (include the namespace 'l' if you are looking for a local id)
  - Once viewing a single node, click other nodes to navigate the graph or return Home to see the list of subject nodes again.

### Design

The files responsible for this application are split into two sections: front-end and back-end. The front-end files, found in `/src/`, use React to implement the user interface. The back-end files, found in `/src/back-end`, serve as the functional implementation of the tool by creating a local version of the Data Commons KG within the browser and incorporates the local data parsed from the passed in files.

##### Back-end

The back-end parses local files to model the Knowledge Graph by creating Node and Assertion objects. TMCF+CSV files are first translated to MCF formatting. MCF files are parsed line by line to create the local version of the KG. When encountering a line beginnig with 'Node:', the parser will create a new Node which will be the subject of all following assertions (triples) until a new line beginning with 'Node:' is reached. When parsing property lines of the MCF, the target entity is checked to see if it is another entity (indicated by a namespace) or a text based value. If it is another entity, then a new Node object is created for that entity and stored as the target of that Assertion. Additionally, an inverse assertion is created between the source and the target which is useful when displaying the graph data.

When nodes are retrieved from the local version of the KG, it is checked to see if the node has a specified dcid. If it does, then it is verified if the dcid exists in the Data Commons KG. Additionally, triples from the DC KG regarding that node are loaded into local memory and also displayed to the user. This is how the local data is overlayed with the local data.

Brief description of each file:
  - graph.js - Contains the implementation of the Node and Assertion classes. Each node represents a single entity within the Data Commons KG and each Assertion represents a triple by storing a source (Node), property(Text), and target(Node or Text).
  - parse-mcf.js - Implements the ParseMcf class which parses an MCF file and creates a local Knowledge Graph using the Node and Assertion classes.
  - parse-tmcf.js - Implements the ParseTmcf class which creates a template string from one TMCF file and fills in the template based on each row of a given CSV file to create an MCF String.
  - utils.js - Contains various helper functions, including those used to query the Data Commons KG.
  - server-api.js - Acts as a wrapper for the functions needed by the front-end so that only this file is imported into the front-end files.

##### Front-end

The front-end of this application has been implemented with React. The application's main state is saved in the App component. This stores the files which have already been loaded in, which node (if any) should be currently displayed, and more. The App component renders the Header component, which gives the user the option to return to the home page or search for a specific Id.

If there is a node that needs to be displayed, then the App component will render the DisplayNode component. This component fetches all of the relevant triples from the back-end and passes them to TriplesTable components (one table for outgoing triples and one for incoming). The TriplesTable component renders the list of triples in a table so that one row of the table corresponds to a single triple.

If there is no node to be displayed, the the App component renders the Home component. If no files have been loaded to the application, the the Home component will soley display the FileEntry componet to prompt the use to upload files. Once files have been uploaded, the Home component displays lists of the loaded files and the subject nodes of each triple within the file(s). The Home component will also display the ParsingErrorsTable component which displays any errors that were encountered in parsing the files. The Home component also has a button which allows the user to reveal a collapsable FileEntry component if they would like to add more files to their KG.

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

### Running Locally + Testing

To run and test locally, you will need node.js and npm installed. If you do not have these, visit [node.js website](https://nodejs.org/en/download/) to download and install node.js, then install npm.

You can run the following commands to ensure you have both node.js and npm installed:
```sh
$ node -v
$ npm -v
```

After forking this repo, ensure you are in `/tools/mcf-browser`,
then run
```sh
$ npm install
```
which will install the packages specified in `package.json`.

After installing node_modules, you can run the tests for the back-end by running
```sh
$ npm run test
```

You can deploy a local version of the application to test the front-end with
```sh
$ npm start
```
