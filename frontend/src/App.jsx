import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  Trash2, 
  RefreshCw, 
  Settings, 
  FileText, 
  CheckCircle, 
  AlertTriangle, 
  Upload, 
  X, 
  LogOut,
  HelpCircle,
  MessageSquare,
  ChevronRight,
  Database
} from 'lucide-react';
import { apiService } from './services/api';
import './App.css';

function App() {
  // Chat States
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Admin Panel States
  const [adminOpen, setAdminOpen] = useState(false);
  const [isAdmin, setIsAdmin] = useState(apiService.isAdminAuthenticated());
  const [adminPassword, setAdminPassword] = useState('');
  const [adminError, setAdminError] = useState(null);
  
  // Knowledge Base States
  const [statusData, setStatusData] = useState({
    files_count: 0,
    chunks_count: 0,
    indexed_files: []
  });
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(null);

  const messagesEndRef = useRef(null);

  // Suggested questions list
  const suggestions = [
    "What schemes are available for MSMEs and Startups?",
    "What are the benefits of getting DPIIT registration?",
    "Tell me about the StartupTN Coimbatore Regional Hub.",
    "What are the key initiatives of StartupTN for 2024?",
    "How can I apply for a startup scheme?"
  ];

  // Fetch vector DB status on mount and when sync completes
  const fetchStatus = async () => {
    try {
      const data = await apiService.getStatus();
      setStatusData(data);
      setError(null);
    } catch (err) {
      console.error("Failed to load DB status", err);
      // Don't show full error if server is just starting up, let chat fail gracefully
    }
  };

  useEffect(() => {
    fetchStatus();
    // Poll status occasionally to keep sidebar updated if documents change
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  // Auto scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Handle user sending message
  const handleSend = async (textToSend) => {
    const text = textToSend || input.trim();
    if (!text) return;

    if (!textToSend) {
      setInput('');
    }

    setError(null);
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: text
    };

    setMessages(prev => [...prev, userMessage]);
    setLoading(true);

    const assistantMessageId = Date.now() + 1;
    const initialAssistantMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      sources: []
    };

    setMessages(prev => [...prev, initialAssistantMessage]);

    try {
      await apiService.chatStream(
        text,
        (chunk) => {
          if (chunk.type === 'sources') {
            setMessages(prev =>
              prev.map(m => m.id === assistantMessageId ? { ...m, sources: chunk.sources } : m)
            );
          } else if (chunk.type === 'content') {
            setLoading(false);
            setMessages(prev =>
              prev.map(m => m.id === assistantMessageId ? { ...m, content: m.content + chunk.content } : m)
            );
          } else if (chunk.type === 'error') {
            setError(chunk.content);
            setMessages(prev =>
              prev.map(m => m.id === assistantMessageId ? { ...m, content: "Error: " + chunk.content, isError: true } : m)
            );
          }
        },
        (err) => {
          console.error(err);
          const errMsg = err.message || "Unable to connect to the AI Assistant. Please try again.";
          setError(errMsg);
          setMessages(prev =>
            prev.map(m => m.id === assistantMessageId ? {
              ...m,
              content: `Error: ${errMsg}`,
              isError: true
            } : m)
          );
          setLoading(false);
        },
        () => {
          setLoading(false);
        }
      );
    } catch (err) {
      console.error(err);
      setError(err.message || "Unable to connect to the AI Assistant. Please try again.");
      setLoading(false);
    }
  };

  // Clear current conversation
  const handleClearChat = () => {
    setMessages([]);
    setError(null);
  };

  // Trigger sync of vector database
  const handleSyncDatabase = async () => {
    setSyncing(true);
    setAdminError(null);
    try {
      const response = await apiService.syncDatabase();
      await fetchStatus();
      const stats = response.sync_stats || {};
      const errors = stats.errors || [];
      if (errors.length > 0) {
        setAdminError(`Sync errors: ${errors.map(e => `${e.file}: ${e.error}`).join('; ')}`);
      }
      if (stats.total_chunks_added > 0) {
        alert(`Database synced successfully! Indexed ${stats.indexed?.length || 0} file(s), added ${stats.total_chunks_added} chunks.`);
      } else if (errors.length > 0) {
        alert(`Sync failed to index documents. Check the error message in the admin panel.`);
      } else if ((stats.skipped?.length || 0) > 0) {
        alert(`All ${stats.skipped.length} PDF(s) are already indexed (${stats.pdfs_indexed_before || stats.skipped.length} files, ${statusData.chunks_count} chunks).`);
      } else if ((stats.pdfs_on_disk || 0) === 0) {
        alert('No PDF files found in the data folder. Upload PDFs first, then sync.');
      } else {
        alert('Sync finished but no chunks were added. Check admin panel for details.');
      }
    } catch (err) {
      setAdminError(err.detail || "Sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  // Handle Admin login request
  const handleAdminLogin = async (e) => {
    e.preventDefault();
    setAdminError(null);
    try {
      await apiService.login(adminPassword);
      setIsAdmin(true);
      setAdminPassword('');
      fetchStatus();
    } catch (err) {
      setAdminError(err.detail || "Incorrect Password");
    }
  };

  // Handle Admin logout
  const handleAdminLogout = () => {
    apiService.logout();
    setIsAdmin(false);
    setAdminError(null);
  };

  // Handle file uploads
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setAdminError("Only PDF files are supported");
      return;
    }

    setUploading(true);
    setAdminError(null);
    setUploadSuccess(null);

    try {
      await apiService.uploadDocument(file);
      setUploadSuccess(`Uploaded "${file.name}" successfully! Indexing now...`);
      const syncResponse = await apiService.syncDatabase();
      await fetchStatus();
      const stats = syncResponse.sync_stats || {};
      const errors = stats.errors || [];
      if (errors.length > 0) {
        setAdminError(`Indexing failed: ${errors.map(e => `${e.file}: ${e.error}`).join('; ')}`);
        setUploadSuccess(null);
      } else if (stats.total_chunks_added > 0) {
        setUploadSuccess(`Uploaded and indexed "${file.name}" (${stats.total_chunks_added} chunks).`);
      } else {
        setUploadSuccess(`Uploaded "${file.name}". File is already indexed.`);
      }
    } catch (err) {
      setAdminError(err.detail || "File upload failed.");
    } finally {
      setUploading(false);
    }
  };

  // Delete Document
  const handleDeleteDocument = async (filename) => {
    if (!window.confirm(`Are you sure you want to delete ${filename}? This will remove it from the knowledge base.`)) {
      return;
    }

    setAdminError(null);
    try {
      await apiService.deleteDocument(filename);
      // Refresh status
      await fetchStatus();
    } catch (err) {
      setAdminError(err.detail || "Failed to delete file");
    }
  };

  // Safe markdown to HTML conversion helper
  const renderMarkdownHTML = (text) => {
    if (!text) return { __html: '' };
    
    // Basic escapes
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    
    // Markdown replacement rules
    html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>');
    html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
    html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Custom handling for lists
    html = html.replace(/^\*\s+(.*?)$/gm, '<li>$1</li>');
    
    // Convert newlines to paragraphs/br
    const lines = html.split('\n');
    const processedLines = lines.map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '<div class="line-gap"></div>';
      if (trimmed.startsWith('<h1>') || trimmed.startsWith('<h2>') || trimmed.startsWith('<h3>') || trimmed.startsWith('<li>')) {
        return line;
      }
      return `<p>${line}</p>`;
    });

    return { __html: processedLines.join('') };
  };

  return (
    <div className="app-container">
      
      {/* SIDEBAR COMPONENT */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">StartupTN</div>
          <div className="subtitle">AI Assistant & Knowledge Hub</div>
        </div>
        
        <div className="sidebar-scroll">
          {/* KB Metrics */}
          <div className="sidebar-section-title">Knowledge Base Status</div>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-val">{statusData.files_count}</div>
              <div className="stat-label">Files Indexed</div>
            </div>
            <div className="stat-card">
              <div className="stat-val">{statusData.chunks_count}</div>
              <div className="stat-label">Text Chunks</div>
            </div>
          </div>

          {/* List of Files */}
          <div className="sidebar-section-title">Indexed Documents</div>
          <div className="doc-list">
            {statusData.indexed_files.length > 0 ? (
              statusData.indexed_files.map((file, idx) => (
                <div className="doc-item" key={idx} title={file}>
                  <span className="doc-name">📄 {file}</span>
                  <span className="doc-badge">Active</span>
                </div>
              ))
            ) : (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', padding: '1rem 0' }}>
                No documents indexed.
              </div>
            )}
          </div>
        </div>

        {/* Footer Actions */}
        <div className="sidebar-footer">
          {isAdmin && (
            <button 
              className="btn-sidebar btn-sync" 
              onClick={handleSyncDatabase} 
              disabled={syncing}
            >
              <RefreshCw className={syncing ? 'animate-spin' : ''} size={16} />
              {syncing ? 'Syncing...' : 'Sync Local PDFs'}
            </button>
          )}

          <button 
            className="btn-sidebar btn-admin" 
            onClick={() => setAdminOpen(true)}
          >
            <Settings size={16} />
            {isAdmin ? 'Admin Dashboard' : 'Admin Area'}
          </button>

          {isAdmin && (
            <button className="btn-sidebar btn-admin-logout" onClick={handleAdminLogout}>
              <LogOut size={16} />
              Logout Admin
            </button>
          )}
        </div>
      </aside>

      {/* MAIN CHAT AREA */}
      <main className="chat-window">
        <header className="chat-header">
          <div className="chat-header-title">
            <h2>StartupTN AI Assistant</h2>
            <p>Interactive assistance for government startup schemes, DPIIT benefits and MSME support.</p>
          </div>
          {messages.length > 0 && (
            <button className="btn-sidebar btn-clear" style={{ width: 'auto', marginBottom: 0 }} onClick={handleClearChat}>
              <Trash2 size={14} style={{ marginRight: '4px' }} />
              Clear Chat
            </button>
          )}
        </header>

        {/* Chat Feed */}
        <div className="messages-container">
          {error && (
            <div className="system-alert error">
              <AlertTriangle size={18} />
              <span>{error}</span>
            </div>
          )}

          {messages.length === 0 ? (
            <div className="empty-chat">
              <div className="empty-chat-logo">
                <Database size={32} />
              </div>
              <h3>How can I assist you today?</h3>
              <p>Ask me about scheme benefits, application processes, eligibility criteria, or documents required for StartupTN initiatives.</p>
              
              <div className="suggestions-grid">
                {suggestions.map((sug, idx) => (
                  <button 
                    key={idx} 
                    className="suggestion-card" 
                    onClick={() => handleSend(sug)}
                  >
                    <MessageSquare size={16} className="suggestion-icon" />
                    <span>{sug}</span>
                    <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div className={`message-row ${msg.role}`} key={msg.id}>
                <div className="message-bubble">
                  {msg.role === 'assistant' ? (
                    <>
                      <div 
                        className="markdown-content" 
                        dangerouslySetInnerHTML={renderMarkdownHTML(msg.content)} 
                      />
                      
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="citations-box">
                          {msg.sources.map((src, sIdx) => (
                            <span className="citation-chip" key={sIdx}>
                              <FileText size={12} />
                              {src}
                            </span>
                          ))}
                        </div>
                      )}
                    </>
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))
          )}

          {loading && (
            <div className="message-row assistant">
              <div className="message-bubble" style={{ padding: '0.75rem 1.25rem' }}>
                <div className="typing-indicator">
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="input-container">
          <div className="input-box-wrapper">
            <textarea
              className="chat-input"
              rows="1"
              placeholder="Ask a question about StartupTN schemes..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={loading}
            />
            <button 
              className="btn-circle btn-send" 
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </main>

      {/* ADMIN CONTROL MODAL */}
      {adminOpen && (
        <div className="admin-overlay">
          <div className="admin-modal">
            <div className="admin-modal-header">
              <h3>Admin Management Panel</h3>
              <button className="btn-close" onClick={() => { setAdminOpen(false); setAdminError(null); setUploadSuccess(null); }}>
                <X size={20} />
              </button>
            </div>
            
            <div className="admin-modal-body">
              {adminError && (
                <div className="system-alert error">
                  <AlertTriangle size={16} />
                  <span>{adminError}</span>
                </div>
              )}
              {uploadSuccess && (
                <div className="system-alert info">
                  <CheckCircle size={16} />
                  <span>{uploadSuccess}</span>
                </div>
              )}

              {!isAdmin ? (
                // Login View
                <div className="admin-login-view">
                  <Database size={48} style={{ color: 'var(--primary)', marginBottom: '1rem' }} />
                  <h4>Authentication Required</h4>
                  <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                    Only administrators can upload documents, sync the database, and manage files.
                  </p>
                  
                  <form onSubmit={handleAdminLogin}>
                    <div className="admin-input-group">
                      <input
                        type="password"
                        className="admin-input"
                        placeholder="Enter Admin Password..."
                        value={adminPassword}
                        onChange={(e) => setAdminPassword(e.target.value)}
                        required
                        autoFocus
                      />
                    </div>
                    <button type="submit" className="btn-primary">
                      Verify Administrator Credentials
                    </button>
                  </form>
                </div>
              ) : (
                // Admin Dashboard Dashboard
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem', alignItems: 'center' }}>
                    <div>
                      <h4 style={{ margin: 0 }}>Knowledge Base Controls</h4>
                      <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Manage PDF training data and vector embeddings.
                      </p>
                    </div>
                    <button 
                      className="btn-sidebar btn-sync" 
                      style={{ width: 'auto', marginBottom: 0, padding: '0.5rem 1rem' }}
                      onClick={handleSyncDatabase}
                      disabled={syncing}
                    >
                      <RefreshCw className={syncing ? 'animate-spin' : ''} size={14} />
                      {syncing ? 'Syncing...' : 'Sync Index'}
                    </button>
                  </div>

                  {/* Upload Zone */}
                  <div className="upload-zone" onClick={() => document.getElementById('admin-file-picker').click()}>
                    <input
                      id="admin-file-picker"
                      type="file"
                      accept=".pdf"
                      style={{ display: 'none' }}
                      onChange={handleFileUpload}
                      disabled={uploading}
                    />
                    <Upload className="upload-zone-icon" />
                    <p className="upload-zone-text">
                      {uploading ? (
                        <span>Uploading file... Please wait.</span>
                      ) : (
                        <span>
                          Drag and drop or <span className="upload-zone-highlight">browse</span> for PDF guidelines
                        </span>
                      )}
                    </p>
                    <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                      Supports official PDF documents up to 50MB
                    </p>
                  </div>

                  {/* Document List for Deletion */}
                  <h5 style={{ marginBottom: '0.5rem', fontWeight: 600 }}>Manage Indexed Files</h5>
                  <div className="admin-doc-list">
                    {statusData.indexed_files.length > 0 ? (
                      statusData.indexed_files.map((file, idx) => (
                        <div className="admin-doc-item" key={idx}>
                          <span className="admin-doc-name" title={file}>📄 {file}</span>
                          <button 
                            className="btn-delete" 
                            onClick={() => handleDeleteDocument(file)}
                            title="Delete file"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>
                        No files in the database.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
