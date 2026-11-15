"use client";

export { AssistantWorkspaceView as AssistantWorkspace } from "./AssistantWorkspaceView";
export default function AssistantWorkspaceDefault() {
  const { AssistantWorkspaceView } = require("./AssistantWorkspaceView");
  return <AssistantWorkspaceView />;
}
