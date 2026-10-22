import { Injectable } from "@angular/core";
import { BehaviorSubject, filter } from "rxjs";
import { BaseMessage, TauriService } from "./tauri.service";

export interface ChatMessage extends BaseMessage {
    type: "chat";
    role: string;
    message: string;
    processingText?: string;
    synthetic?: boolean;
    searchDetails?: string;
    tool_call_id?: string;
    actor_id?: string;
    actor_name?: string;
    avatar_id?: string;
    avatar_url?: string;
    display_name?: string;
    display_color?: string;
    plugin_event_name?: string;
}

export interface ToolEvent {
    kind: 'tool';
    request: any[];
    results: any[];
    text?: string[];
}

export interface ToolProcessingEvent {
    kind: 'tool_processing';
    tool_call_id: string;
    name: string;
    content: any;
    text?: string;
}

export interface EventMessage extends BaseMessage {
    type: 'event';
    event: ToolEvent | ToolProcessingEvent;
}

@Injectable({
    providedIn: "root",
})
export class ChatService {
    private chatHistorySubject = new BehaviorSubject<ChatMessage[]>([]);
    public chatHistory$ = this.chatHistorySubject.asObservable();

    private chatMessageSubject = new BehaviorSubject<ChatMessage | null>(null);
    public chatMessage$ = this.chatMessageSubject.asObservable()

    private searchResultSubject = new BehaviorSubject<any | null>(null);
    public searchResult$ = this.searchResultSubject.asObservable();

    private readonly activeToolActionMessages = new Map<string, ChatMessage>();
    private readonly completedSyntheticActionMessages = new Set<string>();

    constructor(private tauriService: TauriService) {
        // Subscribe to log messages from the TauriService
        this.tauriService.output$.pipe(
            filter((message): message is ChatMessage =>
                message.type === "chat"
            ),
        ).subscribe((chatMessage) => {
            if (chatMessage.type === "chat") {
                if (this.shouldSuppressCompletedSyntheticAction(chatMessage)) {
                    return;
                }
                this.chatMessageSubject.next(chatMessage);
                const currentLogs = this.chatHistorySubject.getValue();
                this.chatHistorySubject.next([...currentLogs, chatMessage]);
            }
        });

        this.tauriService.output$.pipe(
            filter((message): message is EventMessage =>
                message.type === "event" && ["tool", "tool_processing"].includes((message as any).event?.kind)
            ),
        ).subscribe((eventMessage) => {
            if (eventMessage.event.kind === "tool_processing") {
                this.handleToolProcessingEvent(eventMessage, eventMessage.event);
                return;
            }

            const toolEvent = eventMessage.event;
            this.handleFinalToolEvent(toolEvent);
            const webSearchRequestIndex = toolEvent.request.findIndex((r: any) => r.function?.name === 'web_search_agent');
            
            if (webSearchRequestIndex !== -1 && toolEvent.results[webSearchRequestIndex]) {
                const result = toolEvent.results[webSearchRequestIndex];
                const details = typeof result.content === 'string' ? result.content.trim() : JSON.stringify(result, null, 2);
                if (details) {
                    this.chatHistorySubject.next([...this.chatHistorySubject.getValue(), {
                        type: 'chat', role: 'search_result', message: 'Search result',
                        timestamp: eventMessage.timestamp, index: eventMessage.index,
                        searchDetails: details,
                    }]);
                }
                this.searchResultSubject.next(result);
            }
        });
    }

    public clearChat(): void {
        this.chatHistorySubject.next([]);
        this.searchResultSubject.next(null);
        this.activeToolActionMessages.clear();
        this.completedSyntheticActionMessages.clear();
    }

    public getCurrentChat(): ChatMessage[] {
        return this.chatHistorySubject.getValue();
    }

    private handleToolProcessingEvent(eventMessage: EventMessage, event: ToolProcessingEvent): void {
        if (!['web_search_agent', 'generate_overlay_ui'].includes(event.name)) {
            return;
        }

        const content = event.content ?? {};
        const message = this.formatProcessingMessage(event.name, content);
        const processingText = this.formatToolProcessingText(content);
        const currentLogs = this.chatHistorySubject.getValue();
        const existing = this.activeToolActionMessages.get(event.tool_call_id);

        if (existing) {
            const updated: ChatMessage = {
                ...existing,
                message,
                processingText: processingText ?? existing.processingText,
            };
            this.activeToolActionMessages.set(event.tool_call_id, updated);
            this.chatHistorySubject.next(currentLogs.map((item) => item === existing ? updated : item));
            return;
        }

        const syntheticMessage: ChatMessage = {
            type: 'chat',
            timestamp: eventMessage.timestamp,
            index: eventMessage.index,
            role: 'action',
            message,
            processingText,
            synthetic: true,
            tool_call_id: event.tool_call_id,
        };

        this.activeToolActionMessages.set(event.tool_call_id, syntheticMessage);
        this.chatMessageSubject.next(syntheticMessage);
        this.chatHistorySubject.next([...currentLogs, syntheticMessage]);
    }

    private handleFinalToolEvent(event: ToolEvent): void {
        for (const result of event.results ?? []) {
            const toolCallId = result?.tool_call_id;
            if (!toolCallId) {
                continue;
            }
            const existing = this.activeToolActionMessages.get(toolCallId);
            if (!existing) {
                continue;
            }
            this.activeToolActionMessages.delete(toolCallId);
            this.completedSyntheticActionMessages.add(existing.message);
            this.chatHistorySubject.next(this.chatHistorySubject.getValue().filter((item) => item !== existing));
        }
    }

    private formatToolProcessingText(content: any): string | undefined {
        if (typeof content?.internal_tool_name !== 'string') {
            return undefined;
        }
        return 'In progress';
    }

    private formatProcessingMessage(actionName: string, content: any): string {
        if (actionName === 'generate_overlay_ui') {
            return 'Updating display…';
        }

        const query = typeof content?.query === 'string' ? content.query.toLowerCase() : '';
        if (query.includes('fuel')) return 'Checking fuel data…';
        if (query.includes('ship')) return 'Checking ship status…';
        if (query.includes('material')) return 'Searching materials…';
        if (query.includes('station')) return 'Finding nearby stations…';
        return 'Searching…';
    }

    private shouldSuppressCompletedSyntheticAction(chatMessage: ChatMessage): boolean {
        if (chatMessage.role !== 'action' || !this.completedSyntheticActionMessages.has(chatMessage.message)) {
            return false;
        }
        this.completedSyntheticActionMessages.delete(chatMessage.message);
        return true;
    }
}
