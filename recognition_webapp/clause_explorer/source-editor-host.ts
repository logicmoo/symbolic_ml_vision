import { createElement, useEffect, useRef, useState, type ComponentProps } from "react";
import { ResourceSourceEditor as OriginalEditor } from "./upstream/apps/workbench/src/components/ResourceSourceEditor";
import { prepareSources } from "./server-model";

export function ResourceSourceEditor(props: ComponentProps<typeof OriginalEditor>) {
  const revision = useRef(0);
  const [error, setError] = useState("");
  useEffect(() => () => { revision.current++; }, []);
  const onChange = (text: string) => {
    const request = ++revision.current;
    setError("");
    props.onChange(text);
    void prepareSources([{ name: props.sourcePath || "source.pl", text }]).then(() => {
      if (request === revision.current) props.onChange(text);
    }).catch(reason => {
      if (request === revision.current) setError(reason instanceof Error ? reason.message : String(reason));
    });
  };
  return createElement("div", { className: "pce-source-host" },
    createElement(OriginalEditor, { ...props, onChange }),
    error ? createElement("p", { role: "alert" }, error) : null,
  );
}
