/**
 * ChatPage - Three-column layout for the full /chat route.
 *
 * Left: ConversationList | Center: MessageStream + ChatInput | Right: ConversationContext
 */

import { useCallback, useEffect, useState } from "react";
import { getDefaultChatModel } from "../../../components/settings/ChatModelSettings";
import { cn } from "../../../lib/utils";
import {
  useAgentHealth,
  useConversationDetail,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useMessages,
} from "../hooks/useChatQueries";
import { useSSEStream } from "../hooks/useSSEStream";
import { ChatInput } from "./ChatInput";
import { ConversationContext } from "./ConversationContext";
import { ConversationList } from "./ConversationList";
import { MessageStream } from "./MessageStream";

export function ChatPage() {
  const [activeConversationId, setActiveConversationId] = useState<string | undefined>();
  const [model, setModel] = useState(getDefaultChatModel);
  const [actionMode, setActionMode] = useState(false);
  const [contextOpen, setContextOpen] = useState(true);

  // Queries
  const { data: conversations } = useConversations();
  const { data: agentHealthy } = useAgentHealth();
  const { data: activeConversation } = useConversationDetail(activeConversationId);
  const { data: messages, isLoading: messagesLoading } = useMessages(activeConversationId);

  // Mutations
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();

  // Streaming
  const { streamingMessage, toolResults, isStreaming, sendMessage } = useSSEStream();

  // Auto-select first conversation on load (or when conversations change and none is selected)
  useEffect(() => {
    if (!activeConversationId && conversations && conversations.length > 0) {
      setActiveConversationId(conversations[0].id);
    }
  }, [activeConversationId, conversations]);

  const handleCreateConversation = useCallback(async () => {
    try {
      const newConv = await createConversation.mutateAsync({});
      setActiveConversationId(newConv.id);
    } catch {
      // Error logged by mutation hook
    }
  }, [createConversation]);

  const handleDeleteConversation = useCallback(
    (id: string) => {
      deleteConversation.mutate(id);
      if (activeConversationId === id) {
        setActiveConversationId(undefined);
      }
    },
    [deleteConversation, activeConversationId],
  );

  const handleSend = useCallback(
    async (content: string) => {
      let convId = activeConversationId;

      if (!convId) {
        // Create conversation first, wait for it, then send
        const newConv = await createConversation.mutateAsync({});
        convId = newConv.id;
        setActiveConversationId(convId);
      }

      sendMessage(convId, content, model);
    },
    [activeConversationId, sendMessage, model, createConversation],
  );

  return (
    <div className="flex h-[calc(100vh-4rem)] rounded-lg overflow-hidden border border-white/10 backdrop-blur-xl bg-white/5">
      {/* Left: Conversation list */}
      <div className="w-[260px] border-r border-white/10 shrink-0">
        <ConversationList
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={setActiveConversationId}
          onCreate={handleCreateConversation}
          onDelete={handleDeleteConversation}
        />
      </div>

      {/* Center: Messages + Input */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Agent health banner */}
        {agentHealthy === false && (
          <div className={cn("px-4 py-2 text-xs text-center", "bg-red-500/10 border-b border-red-500/20 text-red-300")}>
            Agent service is unavailable. Chat functionality is limited.
          </div>
        )}

        <MessageStream
          messages={messages}
          isLoading={messagesLoading}
          streamingMessage={streamingMessage}
          toolResults={toolResults}
          isStreaming={isStreaming}
        />

        <ChatInput
          onSend={handleSend}
          isStreaming={isStreaming}
          disabled={agentHealthy === false}
          model={model}
          onModelChange={setModel}
          actionMode={actionMode}
          onActionModeChange={setActionMode}
        />
      </div>

      {/* Right: Context panel */}
      <ConversationContext
        conversation={activeConversation}
        isOpen={contextOpen}
        onToggle={() => setContextOpen(!contextOpen)}
        model={model}
        onModelChange={setModel}
        actionMode={actionMode}
        onActionModeChange={setActionMode}
      />
    </div>
  );
}
