"use client";

import { useState, useRef, useEffect } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import ModelSelector from "./ModelSelector";
import { ChatBubble } from "./ds";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Message = {
  role: "user" | "model";
  text: string;
};

type AulaChatProps = {
  aulaId: number;
  disabled?: boolean;
};

export default function AulaChat({ aulaId, disabled = false }: AulaChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [modelo, setModelo] = useState("gemini-3-flash-preview");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading || disabled) return;

    const userMsg: Message = { role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    const assistantMsg: Message = { role: "model", text: "" };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const response = await fetch(`${API_URL}/api/aulas/${aulaId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mensagem: text,
          modelo,
          historico: messages.map((m) => ({ role: m.role, text: m.text })),
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Erro no chat");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === "model") {
                  updated[updated.length - 1] = { ...last, text: last.text + data };
                }
                return updated;
              });
            }
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === "model") {
          updated[updated.length - 1] = {
            ...last,
            text: `Erro: ${err instanceof Error ? err.message : "Falha na conexão"}`,
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-surface-dark border border-border-dark rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-dark">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">forum</span>
          <h3 className="text-sm font-semibold text-white">Dúvidas da Aula</h3>
        </div>
        <ModelSelector value={modelo} onChange={setModelo} compact />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-8">
            <span className="material-symbols-outlined text-5xl text-primary/30">smart_toy</span>
            <p className="text-sm text-gray-500">
              Pergunte qualquer coisa sobre esta aula.
              <br />O tutor tem acesso ao conteúdo completo do PDF.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatBubble key={i} role={msg.role}>
            {msg.role === "model" ? (
              <MarkdownRenderer content={msg.text || "..."} />
            ) : (
              msg.text
            )}
          </ChatBubble>
        ))}

        {loading && <ChatBubble typing />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border-dark p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Aguarde o processamento..." : "Pergunte sobre a aula..."}
            disabled={disabled || loading}
            rows={1}
            className="flex-1 bg-gray-800/50 border border-border-dark rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-600 resize-none focus:ring-1 focus:ring-primary focus:border-primary disabled:opacity-40"
            style={{ maxHeight: "120px" }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = "auto";
              target.style.height = Math.min(target.scrollHeight, 120) + "px";
            }}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || loading || disabled}
            className="p-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
          >
            <span className="material-symbols-outlined text-[20px]">send</span>
          </button>
        </div>
      </div>
    </div>
  );
}
