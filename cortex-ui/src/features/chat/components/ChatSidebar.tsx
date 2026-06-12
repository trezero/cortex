/**
 * ChatSidebar - Slide-in panel from the right overlaying the page.
 *
 * Contains: conversation dropdown, MessageStream, and ChatInput.
 * Provides "Expand" button to navigate to /chat and a close (X) button.
 */

import { Expand, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDefaultChatModel } from "../../../components/settings/ChatModelSettings";
import { cn } from "../../../lib/utils";
import {
  useAgentHealth,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useMessages,
} from "../hooks/useChatQueries";
import { useSSEStream } from "../hooks/useSSEStream";
import { ChatInput } from "./ChatInput";
import { ConversationList } from "./ConversationList";
import { MessageStream } from "./MessageStream";

interface ChatSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ChatSidebar({ isOpen, onClose }: ChatSidebarProps) {
  const navigate = useNavigate();
  const [activeConversationId, setActiveConversationId] = useState<string | undefined>();
  const [model, setModel] = useState(getDefaultChatModel);
  const [actionMode, setActionMode] = useState(false);
  const [showConversationList, setShowConversationList] = useState(false);

  // Queries
  const { data: conversations } = useConversations();
  const { data: agentHealthy } = useAgentHealth();
  const { data: messages, isLoading: messagesLoading } = useMessages(activeConversationId);

  // Mutations
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();

  // Streaming
  const { streamingMessage, toolResults, isStreaming, sendMessage } = useSSEStream();

  // Auto-select first conversation if none active
  useEffect(() => {
    if (!activeConversationId && conversations && conversations.length > 0) {
      setActiveConversationId(conversations[0].id);
    }
  }, [activeConversationId, conversations]);

  const handleCreateConversation = useCallback(async () => {
    try {
      const newConv = await createConversation.mutateAsync({});
      setActiveConversationId(newConv.id);
      setShowConversationList(false);
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
        const newConv = await createConversation.mutateAsync({});
        convId = newConv.id;
        setActiveConversationId(convId);
      }

      sendMessage(convId, content, model);
    },
    [activeConversationId, sendMessage, model, createConversation],
  );

  const handleExpand = useCallback(() => {
    onClose();
    navigate("/chat");
  }, [onClose, navigate]);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40" onClick={onClose} />

      {/* Panel */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-[400px] z-50 flex flex-col",
          "backdrop-blur-xl bg-gray-950/95 border-l border-white/10",
          "shadow-[-10px_0_40px_rgba(0,0,0,0.5)]",
          "animate-in slide-in-from-right duration-300",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <div className="flex items-center gap-2">
            <img src="/logo-neon.png" alt="Cortex" className="w-5 h-5" />
            <span className="text-sm font-medium text-gray-200">Cortex Chat</span>
            {agentHealthy === false && (
              <span className="text-[10px] text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">Offline</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setShowConversationList(!showConversationList)}
              className="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors text-xs"
            >
              {conversations?.length ?? 0} chats
            </button>
            <button
              type="button"
              onClick={handleExpand}
              className="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors"
              title="Open full chat page"
            >
              <Expand className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Conversation list (togglable) */}
        {showConversationList && (
          <div className="border-b border-white/10 max-h-[300px] overflow-hidden">
            <ConversationList
              conversations={conversations}
              activeId={activeConversationId}
              onSelect={(id) => {
                setActiveConversationId(id);
                setShowConversationList(false);
              }}
              onCreate={handleCreateConversation}
              onDelete={handleDeleteConversation}
            />
          </div>
        )}

        {/* Message stream */}
        <MessageStream
          messages={messages}
          isLoading={messagesLoading}
          streamingMessage={streamingMessage}
          toolResults={toolResults}
          isStreaming={isStreaming}
        />

        {/* Input */}
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
    </>
  );
}
