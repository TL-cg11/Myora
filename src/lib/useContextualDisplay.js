import { useEffect, useState } from 'react';
import { maskDisplayMessage } from './api.js';
import { finishContextualDisplay, maskForDisplay } from './privacy.js';

/** 원문을 먼저 노출하지 않고 서버의 동일 문맥 모델 결과로 사용자 말풍선을 교체한다. */
export function useContextualMessages(initialMessages) {
  const [messages, setMessages] = useState(initialMessages);

  useEffect(() => {
    const pending = messages.filter(
      (message) => message.role === 'user' && !message.displayChecked,
    );
    if (!pending.length) return undefined;
    let cancelled = false;

    Promise.all(pending.map(async (message) => {
      try {
        const result = await maskDisplayMessage(message.content);
        return [message, finishContextualDisplay(result.display_text)];
      } catch {
        return [message, maskForDisplay(message.content)];
      }
    })).then((updates) => {
      if (cancelled) return;
      const byMessage = new Map(updates);
      setMessages((current) => current.map((message) => (
        byMessage.has(message)
          ? { ...message, content: byMessage.get(message), displayChecked: true }
          : message
      )));
    });

    return () => { cancelled = true; };
  }, [messages]);

  return [messages, setMessages];
}

export function displayMessageContent(message) {
  if (message.role !== 'user' || message.displayChecked) return message.content;
  return maskForDisplay(message.content);
}
