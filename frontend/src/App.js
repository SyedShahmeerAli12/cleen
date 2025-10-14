import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isLoading) return;

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    // Create AI message placeholder for typing animation
    const aiMessageId = Date.now() + 1;
    const aiMessage = {
      id: aiMessageId,
      type: 'ai',
      content: '',
      sources: [],
      timestamp: new Date(),
      isTyping: true
    };

    setMessages(prev => [...prev, aiMessage]);

    try {
      const response = await axios.post(`${API_URL}/query`, { 
        query: inputMessage 
      });

      // Simulate typing animation
      const fullAnswer = response.data.answer;
      const sources = response.data.sources || [];
      
      // Type out the answer character by character
      let currentContent = '';
      for (let i = 0; i <= fullAnswer.length; i++) {
        currentContent = fullAnswer.substring(0, i);
        
        setMessages(prev => prev.map(msg => 
          msg.id === aiMessageId 
            ? { ...msg, content: currentContent, isTyping: i < fullAnswer.length, sources: sources }
            : msg
        ));
        
        // Small delay for typing effect
        if (i < fullAnswer.length) {
          await new Promise(resolve => setTimeout(resolve, 20));
        }
      }

    } catch (error) {
      const errorMessage = {
        id: aiMessageId,
        type: 'ai',
        content: `Error: ${error.message}`,
        sources: [],
        timestamp: new Date(),
        isTyping: false
      };
      setMessages(prev => prev.map(msg => 
        msg.id === aiMessageId ? errorMessage : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  const startNewChat = () => {
    setMessages([]);
  };

  const formatTime = (timestamp) => {
    return timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <div className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon">RAG</div>
            <span>Personal RAG</span>
          </div>
          <button 
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            ←
          </button>
        </div>

        <button className="new-chat-btn" onClick={startNewChat}>
          <span className="new-chat-icon">+</span>
          New Chat
        </button>

        <div className="sidebar-content">
          <div className="sidebar-section">
            <h3>Chat History</h3>
            <div className="chat-history">
              {messages.length === 0 ? (
                <p className="no-chats">No conversations yet</p>
              ) : (
                <div className="chat-item active">
                  <span className="chat-title">Current Chat</span>
                  <span className="chat-time">{formatTime(new Date())}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="main-content">
        {messages.length === 0 ? (
          <div className="welcome-screen">
            <div className="welcome-logo">
              <div className="logo-icon">RAG</div>
            </div>
            <h1>Let's get started.</h1>
            <p>Ask me anything about your documents!</p>
          </div>
        ) : (
          <div className="chat-messages">
            {messages.map((message) => (
              <div key={message.id} className={`message ${message.type}`}>
                <div className="message-content">
                  <div className="message-text">
                    {message.content.split('\n').map((line, index) => {
                      // Format markdown-like text
                      let formattedLine = line;
                      
                      // Bold text **text**
                      formattedLine = formattedLine.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                      
                      // Bullet points * item
                      if (line.trim().startsWith('* ')) {
                        formattedLine = `<span class="bullet-point">• ${line.trim().substring(2)}</span>`;
                      }
                      
                      // Headers ### Header
                      if (line.trim().startsWith('### ')) {
                        formattedLine = `<h3>${line.trim().substring(4)}</h3>`;
                      }
                      
                      return (
                        <div 
                          key={index} 
                          dangerouslySetInnerHTML={{ __html: formattedLine }}
                          className={message.isTyping ? 'typing-text' : ''}
                        />
                      );
                    })}
                  </div>
                  {message.sources && message.sources.length > 0 && (
                    <div className="message-sources">
                      <strong>Sources:</strong>
                      <ul>
                        {message.sources.map((source, index) => (
                          <li key={index}>{source}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="message-time">{formatTime(message.timestamp)}</div>
                </div>
              </div>
            ))}
            
            {isLoading && (
              <div className="message ai">
                <div className="message-content">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <div className="message-time">{formatTime(new Date())}</div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Input Area */}
        <div className="input-area">
          <form onSubmit={handleSendMessage} className="message-form">
            <div className="input-container">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="How can I help you today?"
                className="message-input"
                disabled={isLoading}
              />
              <button 
                type="submit" 
                className="send-button"
                disabled={isLoading || !inputMessage.trim()}
              >
                <span className="send-icon">↑</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default App;