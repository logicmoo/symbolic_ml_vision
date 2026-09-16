import { createElement, type ComponentProps } from "react";
import CodeMirror from "codemirror-upstream";
import { EditorView } from "@codemirror/view";

export default function StandaloneCodeMirror(props: ComponentProps<typeof CodeMirror>) {
  const nonce = document.querySelector<HTMLMetaElement>('meta[name="clause-explorer-style-nonce"]')?.content;
  if (!nonce) throw new Error("The server did not supply the editor's style nonce. Reload the page.");
  return createElement(CodeMirror, {
    ...props,
    extensions: [...(props.extensions || []), EditorView.cspNonce.of(nonce)],
  });
}
