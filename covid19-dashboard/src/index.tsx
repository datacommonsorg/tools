import React from 'react';
import ReactDOM from 'react-dom';
import dashboard from './App';
import * as serviceWorker from './serviceWorker';
import { Route, Router } from 'react-router-dom';
import { createBrowserHistory } from 'history';

const history = createBrowserHistory()

ReactDOM.render(
  <React.StrictMode>
    <Router history={history}>
      <Route path={"/:geoId"} component={dashboard}/>
      <Route exact path={"/"} component={dashboard}/>
    </Router>
  </React.StrictMode>,
  document.getElementById('root')
);

// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.unregister();
