import { ChatMessage } from "../../services/chat.service";

export type ToolPresentation = "result" | "transient" | "diagnostic" | "message";

/** Classify existing chat roles without changing the backend event stream. */
export function toolPresentation(message: ChatMessage): ToolPresentation {
    if (message.role === "search_result") return "result";
    if (message.role === "action") {
        return message.synthetic && !!message.processingText ? "transient" : "diagnostic";
    }
    return "message";
}

export function visibleInNormalChat(message: ChatMessage): boolean {
    return toolPresentation(message) !== "diagnostic";
}
