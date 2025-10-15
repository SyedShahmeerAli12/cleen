import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  MessageCircle, 
  Plus, 
  Send, 
  Bot, 
  User, 
  Sparkles, 
  FileText,
  Clock,
  ChevronLeft,
  ChevronRight,
  Zap,
  Brain,
  Search
} from 'lucide-react';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const startNewChat = () => {
    setMessages([]);
    setSessionId(null);
  };

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
        query: inputMessage,
        session_id: sessionId
      });

      // Store session ID for future requests
      if (response.data.session_id) {
        setSessionId(response.data.session_id);
      }
      
      // Simulate typing animation
      const fullAnswer = response.data.answer;
      const sources = response.data.sources || [];
      const usedDocuments = response.data.used_documents;
      const usedChatContext = response.data.used_chat_context;
      
      // Show answer instantly for better UX (no typing animation delay)
      setMessages(prev => prev.map(msg => 
        msg.id === aiMessageId 
          ? { 
              ...msg, 
              content: fullAnswer, 
              isTyping: false, 
              sources: sources,
              usedDocuments: usedDocuments,
              usedChatContext: usedChatContext
            }
          : msg
      ));

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

  const formatTime = (timestamp) => {
    return timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex h-screen bg-gradient-to-br from-gray-50 via-white to-gray-100 overflow-hidden">
      {/* Sidebar */}
      <motion.div 
        initial={false}
        animate={{ width: sidebarOpen ? 320 : 80 }}
        className="relative flex flex-col bg-gradient-to-b from-gray-800 via-gray-700 to-gray-800 border-r border-gray-600 transition-all duration-300 ease-in-out shadow-xl"
      >
        {/* Sidebar Header */}
        <div className="p-6 border-b border-gray-600">
          <div className="flex items-center justify-between">
            <motion.div 
              className="flex items-center space-x-3"
              animate={{ opacity: sidebarOpen ? 1 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <div className="relative">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center shadow-lg">
                  <Brain className="w-6 h-6 text-white" />
                </div>
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-gradient-to-r from-yellow-400 to-orange-500 rounded-full flex items-center justify-center">
                  <Sparkles className="w-2.5 h-2.5 text-white" />
                </div>
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Personal RAG</h1>
                <p className="text-sm text-gray-300">AI Assistant</p>
              </div>
            </motion.div>
            
            <button 
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 rounded-lg bg-gray-600 hover:bg-gray-500 transition-colors duration-200"
            >
              {sidebarOpen ? <ChevronLeft className="w-5 h-5 text-white" /> : <ChevronRight className="w-5 h-5 text-white" />}
            </button>
          </div>
        </div>

        {/* New Chat Button */}
        <div className="p-4">
          <motion.button 
            onClick={startNewChat}
            className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white font-medium px-6 py-3 rounded-xl transition-all duration-200 shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 flex items-center justify-center space-x-2"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Plus className="w-5 h-5" />
            {sidebarOpen && <span>New Chat</span>}
          </motion.button>
        </div>

        {/* Chat History */}
        <div className="flex-1 px-4 overflow-y-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: sidebarOpen ? 1 : 0, y: sidebarOpen ? 0 : 20 }}
            transition={{ duration: 0.3 }}
          >
            <h3 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">Chat History</h3>
            <div className="space-y-2">
              {messages.length === 0 ? (
                <div className="text-center py-8">
                  <MessageCircle className="w-8 h-8 text-gray-500 mx-auto mb-2" />
                  <p className="text-sm text-gray-400">No conversations yet</p>
                </div>
              ) : (
                <motion.div 
                  className="p-3 rounded-xl bg-gray-600 hover:bg-gray-500 transition-colors duration-200 cursor-pointer border border-gray-500"
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <MessageCircle className="w-4 h-4 text-gray-300" />
                      <span className="text-sm font-medium text-white">Current Chat</span>
                    </div>
                    <Clock className="w-3 h-3 text-gray-400" />
                  </div>
                  <p className="text-xs text-gray-400 mt-1">{formatTime(new Date())}</p>
                </motion.div>
              )}
            </div>
          </motion.div>
        </div>

        {/* Sidebar Footer */}
        <div className="p-4 border-t border-gray-600">
          <motion.div 
            className="flex items-center space-x-3 p-3 rounded-xl bg-gray-600"
            animate={{ opacity: sidebarOpen ? 1 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-blue-500 rounded-lg flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">AI Powered</p>
              <p className="text-xs text-gray-300">Ready to help</p>
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {messages.length === 0 ? (
          <motion.div 
            className="flex-1 flex flex-col items-center justify-center p-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <motion.div 
              className="text-center max-w-2xl"
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.5, delay: 0.2 }}
            >
              <div className="relative mb-8">
                <div className="w-24 h-24 bg-gradient-to-br from-primary-500 to-accent-500 rounded-3xl flex items-center justify-center mx-auto shadow-2xl">
                  <Brain className="w-12 h-12 text-white" />
                </div>
                <motion.div 
                  className="absolute -top-2 -right-2 w-8 h-8 bg-gradient-to-r from-yellow-400 to-orange-500 rounded-full flex items-center justify-center"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                >
                  <Sparkles className="w-4 h-4 text-white" />
                </motion.div>
              </div>
              
              <h1 className="text-4xl font-bold gradient-text mb-4 text-shadow-lg">
                Welcome to Personal RAG
              </h1>
              <p className="text-xl text-gray-600 mb-8 leading-relaxed">
                Your intelligent document assistant powered by AI. Ask me anything about your documents!
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl">
                <motion.div 
                  className="p-6 bg-white rounded-2xl shadow-lg border border-gray-100"
                  whileHover={{ y: -5, shadow: "0 20px 40px rgba(0,0,0,0.1)" }}
                  transition={{ duration: 0.2 }}
                >
                  <Search className="w-8 h-8 text-primary-500 mb-3" />
                  <h3 className="font-semibold text-gray-800 mb-2">Smart Search</h3>
                  <p className="text-sm text-gray-600">Find information instantly across all your documents</p>
                </motion.div>
                
                <motion.div 
                  className="p-6 bg-white rounded-2xl shadow-lg border border-gray-100"
                  whileHover={{ y: -5, shadow: "0 20px 40px rgba(0,0,0,0.1)" }}
                  transition={{ duration: 0.2 }}
                >
                  <FileText className="w-8 h-8 text-accent-500 mb-3" />
                  <h3 className="font-semibold text-gray-800 mb-2">Document Analysis</h3>
                  <p className="text-sm text-gray-600">Get insights and summaries from your content</p>
                </motion.div>
                
                <motion.div 
                  className="p-6 bg-white rounded-2xl shadow-lg border border-gray-100"
                  whileHover={{ y: -5, shadow: "0 20px 40px rgba(0,0,0,0.1)" }}
                  transition={{ duration: 0.2 }}
                >
                  <Bot className="w-8 h-8 text-green-500 mb-3" />
                  <h3 className="font-semibold text-gray-800 mb-2">AI Assistant</h3>
                  <p className="text-sm text-gray-600">Natural conversations with your documents</p>
                </motion.div>
              </div>
            </motion.div>
          </motion.div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <AnimatePresence>
              {messages.map((message, index) => (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3, delay: index * 0.1 }}
                  className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`flex items-start space-x-3 max-w-3xl ${message.type === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      message.type === 'user' 
                        ? 'bg-gradient-to-br from-primary-500 to-primary-600' 
                        : 'bg-gradient-to-br from-gray-100 to-gray-200'
                    }`}>
                      {message.type === 'user' ? (
                        <User className="w-4 h-4 text-white" />
                      ) : (
                        <Bot className="w-4 h-4 text-gray-600" />
                      )}
                    </div>
                    
                    <div className={`p-4 rounded-2xl ${
                      message.type === 'user' 
                        ? 'chat-bubble-user' 
                        : 'chat-bubble-ai'
                    }`}>
                      <div className="prose prose-sm max-w-none">
                        {message.content.split('\n').map((line, lineIndex) => {
                          let formattedLine = line;
                          
                          // Headers ### Header (check first)
                          if (line.trim().startsWith('### ')) {
                            formattedLine = `<h3 class="text-lg font-semibold mb-3 text-gray-800 border-b border-gray-200 pb-1">${line.trim().substring(4)}</h3>`;
                          }
                          // Headers ## Header
                          else if (line.trim().startsWith('## ')) {
                            formattedLine = `<h2 class="text-xl font-bold mb-3 text-gray-900">${line.trim().substring(3)}</h2>`;
                          }
                          // Headers # Header
                          else if (line.trim().startsWith('# ')) {
                            formattedLine = `<h1 class="text-2xl font-bold mb-4 text-gray-900">${line.trim().substring(2)}</h1>`;
                          }
                          // Bullet points * item
                          else if (line.trim().startsWith('* ')) {
                            formattedLine = `<div class="flex items-start mb-2"><span class="mr-2 text-primary-500 font-bold">•</span><span>${line.trim().substring(2)}</span></div>`;
                          }
                          // Numbered lists 1. item
                          else if (/^\d+\.\s/.test(line.trim())) {
                            formattedLine = `<div class="flex items-start mb-2"><span class="mr-2 text-primary-500 font-bold">${line.trim().split('.')[0]}.</span><span>${line.trim().substring(line.trim().indexOf(' ') + 1)}</span></div>`;
                          }
                          // Bold text **text** (do this last)
                          else {
                            formattedLine = formattedLine.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-800">$1</strong>');
                          }
                          
                          return (
                            <div 
                              key={lineIndex} 
                              dangerouslySetInnerHTML={{ __html: formattedLine }}
                              className={message.isTyping ? 'animate-pulse' : ''}
                            />
                          );
                        })}
                      </div>
                      

        {message.sources && message.sources.length > 0 && (
          <motion.div 
            className="mt-4 pt-4 border-t border-gray-200"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            <div className="flex items-center space-x-2 mb-3">
              {message.usedChatContext ? (
                <Brain className="w-4 h-4 text-purple-500" />
              ) : (
                <FileText className="w-4 h-4 text-gray-500" />
              )}
              <span className="text-sm font-medium text-gray-600">
                {message.usedChatContext ? "Chat Context:" : "Sources:"}
              </span>
              {message.usedChatContext && (
                <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded-full">
                  Using Memory
                </span>
              )}
            </div>
                          <div className="flex flex-wrap gap-2">
                            {message.sources.map((source, index) => (
                              <div
                                key={index}
                                className="group relative"
                              >
                                <button
                                  className="flex items-center space-x-2 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs rounded-lg border border-blue-200 hover:border-blue-300 transition-all duration-200 hover:shadow-md"
                                  title={`Click to open: ${source}`}
                                  onClick={() => {
                                    // Open URL in new tab
                                    window.open(source, '_blank', 'noopener,noreferrer');
                                  }}
                                >
                                  <span className="text-base">🔗</span>
                                  <span className="font-medium">{source}</span>
                                </button>
                                {/* Tooltip */}
                                <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-10">
                                  {source}
                                  <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-gray-800"></div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                      
                      <div className={`text-xs mt-2 ${
                        message.type === 'user' ? 'text-white/70' : 'text-gray-500'
                      }`}>
                        {formatTime(message.timestamp)}
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            
            {isLoading && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex justify-start"
              >
                <div className="flex items-start space-x-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-gray-600" />
                  </div>
                  <div className="p-4 bg-white border border-gray-200 rounded-2xl rounded-bl-md shadow-sm">
                    <div className="typing-dots">
                      <div className="typing-dot"></div>
                      <div className="typing-dot"></div>
                      <div className="typing-dot"></div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Input Area */}
        <div className="p-6 border-t border-gray-200 bg-white/50 backdrop-blur-sm">
          <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto">
            <div className="relative">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="Ask me anything about your documents..."
                className="w-full px-6 py-4 pr-16 bg-white border border-gray-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all duration-200 placeholder-gray-400 shadow-lg"
                disabled={isLoading}
              />
              <motion.button 
                type="submit" 
                disabled={isLoading || !inputMessage.trim()}
                className="absolute right-2 top-2 bottom-2 px-4 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Send className="w-5 h-5" />
              </motion.button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default App;