import React, { useEffect, useMemo, useRef, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";

const APP_NAME = "AbhayAI";
const APP_TAGLINE = "Your personal tech assistant by Abhay";

const QUICK_ACTIONS = [
];

function formatTimestamp(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "invalid time";
  }
  return date.toLocaleString();
}

function Message({ role, content, timestamp }) {
  return React.createElement(
    "div",
    { className: `message-row ${role}` },
    React.createElement(
      "div",
      { className: `message ${role}` },
      React.createElement("div", null, content),
      React.createElement(
        "div",
        { className: "meta" },
        `${role} • ${formatTimestamp(timestamp)}`
      )
    )
  );
}

function AppHeader() {
  return React.createElement(
    "header",
    { className: "hero" },
    React.createElement(
      "h1",
      null,
      React.createElement("span", { className: "brand" }, APP_NAME),
      " — What can I help with?"
    ),
    React.createElement("p", null, APP_TAGLINE)
  );
}

function formatChatPreview(chat) {
  const title = chat.title || "New chat";
  const count = Number.isFinite(chat.message_count) ? chat.message_count : 0;
  const stamp = chat.updated_at ? formatTimestamp(chat.updated_at) : "";
  const suffix = stamp ? ` • ${stamp}` : "";
  return `${title} (${count})${suffix}`;
}

function App() {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const chatBoxRef = useRef(null);

  useEffect(() => {
    async function bootstrap() {
      try {
        const loadedChats = await refreshChats();
        if (loadedChats.length === 0) {
          const created = await createNewChat();
          if (created?.id) {
            await loadChat(created.id);
          }
          return;
        }

        const selectedId = loadedChats[0].id;
        await loadChat(selectedId);
      } catch (error) {
        console.error(error);
        setMessages([
          {
            role: "assistant",
            content: "Error: could not load chats.",
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    }

    bootstrap();
  }, []);

  useEffect(() => {
    if (chatBoxRef.current) {
      chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight;
    }
  }, [messages]);

  const hasMessages = useMemo(() => messages.length > 0, [messages]);

  async function refreshChats() {
    const res = await fetch("/api/chats");
    const data = await res.json();
    const loadedChats = Array.isArray(data.chats) ? data.chats : [];
    setChats(loadedChats);
    return loadedChats;
  }

  async function createNewChat() {
    const res = await fetch("/api/chats", { method: "POST" });
    const data = await res.json();
    const created = data.chat || null;
    await refreshChats();
    return created;
  }

  async function loadChat(chatId) {
    if (!chatId) {
      return;
    }

    setIsLoadingChat(true);
    try {
      const res = await fetch(`/api/chats/${chatId}`);
      const data = await res.json();
      const chat = data.chat;
      setActiveChatId(chatId);
      setMessages(Array.isArray(chat?.messages) ? chat.messages : []);
    } catch (error) {
      console.error(error);
      setMessages([
        {
          role: "assistant",
          content: "Error: could not load selected chat.",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoadingChat(false);
    }
  }

  async function sendMessage(content) {
    const trimmed = content.trim();
    if (!trimmed || isSending || !activeChatId) {
      return;
    }

    const optimisticUserMessage = {
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimisticUserMessage]);
    setIsSending(true);

    try {
      const res = await fetch(`/api/chats/${activeChatId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });

      if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          timestamp: new Date().toISOString(),
        },
      ]);
      await refreshChats();
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error: could not reach local API.",
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    await sendMessage(messageInput);
    setMessageInput("");
  }

  async function handleQuickAction(prompt) {
    setMessageInput(prompt);
    await sendMessage(prompt);
    setMessageInput("");
  }

  async function handleClear() {
    try {
      await fetch("/api/history", { method: "DELETE" });
      setMessages([]);
      await refreshChats();
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error: could not clear history.",
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  }

  async function handleCreateNewChat() {
    try {
      const created = await createNewChat();
      if (!created?.id) {
        return;
      }
      setActiveChatId(created.id);
      setMessages([]);
      await loadChat(created.id);
    } catch (error) {
      console.error(error);
    }
  }

  async function handleDeleteChat(chatId, event) {
    event.stopPropagation();

    try {
      const res = await fetch(`/api/chats/${chatId}`, { method: "DELETE" });
      const data = await res.json();

      if (!res.ok || data.status === "not_found") {
        throw new Error("Delete failed");
      }

      const loadedChats = await refreshChats();
      const nextActiveId = data.active_chat_id || loadedChats[0]?.id || null;

      if (!nextActiveId) {
        const created = await createNewChat();
        if (created?.id) {
          await loadChat(created.id);
        } else {
          setActiveChatId(null);
          setMessages([]);
        }
        return;
      }

      if (chatId === activeChatId || !loadedChats.some((chat) => chat.id === activeChatId)) {
        await loadChat(nextActiveId);
      }
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error: could not delete chat.",
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  }

  let chatContent = React.createElement(
    "section",
    { className: "empty-state" },
    React.createElement("p", null, "Start a new chat from the left panel.")
  );

  if (isLoadingChat) {
    chatContent = React.createElement(
      "section",
      { className: "empty-state" },
      React.createElement("p", null, "Loading chat...")
    );
  } else if (hasMessages) {
    chatContent = React.createElement(
      "section",
      { id: "chatBox", className: "chat-box", "aria-live": "polite", ref: chatBoxRef },
      ...messages.map((msg, index) =>
        React.createElement(Message, {
          key: `${msg.role}-${msg.timestamp}-${index}`,
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp,
        })
      )
    );
  }

  return React.createElement(
    "main",
    { className: "app-shell" },
    React.createElement(
      "aside",
      { className: "sidebar" },
      React.createElement("h2", null, "Chats"),
      React.createElement(
        "div",
        { className: "sidebar-actions" },
      React.createElement(
        "button",
        { className: "new-chat-btn", type: "button", onClick: handleCreateNewChat },
        "+ Create New Chat"
      ),
      React.createElement(
        "button",
        {
          className: "clear-chat-btn",
          type: "button",
          onClick: handleClear,
          disabled: !activeChatId || isSending,
        },
        "Clear Current Chat"
      )
      ),
      React.createElement(
        "div",
        { className: "history-list" },
        ...chats.map((chat) =>
          React.createElement(
            "div",
            {
              key: chat.id,
              className: `history-item ${chat.id === activeChatId ? "active" : ""}`,
            },
            React.createElement(
              "button",
              {
                type: "button",
                className: "history-select-btn",
                onClick: () => loadChat(chat.id),
              },
              React.createElement("span", { className: "history-text" }, formatChatPreview(chat))
            ),
            React.createElement(
              "button",
              {
                type: "button",
                className: "delete-chat-icon",
                title: "Delete chat",
                "aria-label": `Delete ${chat.title || "chat"}`,
                onClick: (event) => handleDeleteChat(chat.id, event),
              },
              "🗑"
            )
          )
        )
      )
    ),
    React.createElement(
      "section",
      { className: "main-panel" },
      React.createElement(AppHeader),
      chatContent,
      React.createElement(
        "form",
        { id: "chatForm", className: "composer", onSubmit: handleSubmit },
        React.createElement(
          "div",
          { className: "composer-input" },
          React.createElement("input", {
            id: "messageInput",
            name: "message",
            type: "text",
            placeholder: "Ask anything",
            maxLength: 1000,
            required: true,
            value: messageInput,
            onChange: (event) => setMessageInput(event.target.value),
          }),
          React.createElement(
            "button",
            { type: "submit", className: "send", disabled: isSending || !activeChatId },
            isSending ? "..." : "Go"
          )
        ),
        React.createElement(
          "div",
          { className: "quick-actions" },
          ...QUICK_ACTIONS.map((item) =>
            React.createElement(
              "button",
              {
                key: item.label,
                className: "chip",
                type: "button",
                onClick: () => handleQuickAction(item.prompt),
              },
              item.label
            )
          )
        )
      )
    )
  );
}

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Missing root element in index.html");
}

createRoot(rootElement).render(React.createElement(App));

