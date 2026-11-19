import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

const root = document.getElementById("main");
if (root === null) throw new Error("expected <main id=\"main\"> in index.html");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
