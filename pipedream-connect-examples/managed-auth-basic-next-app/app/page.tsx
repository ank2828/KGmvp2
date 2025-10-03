/* eslint-disable @next/next/no-img-element */
"use client"

import { ErrorBoundary } from "./ErrorBoundary";
import { useEffect, useState, useRef, useCallback } from "react";
import { serverConnectTokenCreate, getAccountById } from "./server"
import type { GetAppResponse, App, PipedreamClient as FrontendClient } from "@pipedream/sdk/browser";
import { useAuth } from "@/contexts/AuthContext";

const frontendHost = process.env.NEXT_PUBLIC_PIPEDREAM_FRONTEND_HOST || "pipedream.com"
const apiHost = process.env.NEXT_PUBLIC_PIPEDREAM_API_HOST || "api.pipedream.com"

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  facts_count?: number;
}

export default function Home() {
  // Supabase Auth
  const { user, loading: authLoading, signInWithGoogle, signOut } = useAuth();

  // Core Pipedream Connect state
  const [externalUserId, setExternalUserId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null)
  const [connectLink, setConnectLink] = useState<string | null>(null)
  const [expiresAt, setExpiresAt] = useState<Date | null>(null)
  const [pd, setPd] = useState<FrontendClient | null>(null);

  // Selected app and connection state
  const [selectedApp, setSelectedApp] = useState<GetAppResponse | null>(null);
  const [appSlug, setAppSlug] = useState<string>("");
  const [accountId, setAccountId] = useState<string | null>(null)
  const [accountName, setAccountName] = useState<string | null>(null)
  const [isOAuthConfirmed, setIsOAuthConfirmed] = useState(false);

  // UI state
  const [error, setError] = useState<string>("");

  // Connection persistence state
  const [storedAccountId, setStoredAccountId] = useState<string | null>(null);
  const [isCheckingConnection, setIsCheckingConnection] = useState(true);

  // App search dropdown state
  const [searchResults, setSearchResults] = useState<App[]>([]);
  const [showDropdown, setShowDropdown] = useState<boolean>(false);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreApps, setHasMoreApps] = useState(true);
  const [currentQuery, setCurrentQuery] = useState<string>("");
  const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null);

  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationHistory, setConversationHistory] = useState<Array<{role: string, content: string}>>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingEmails, setFetchingEmails] = useState(false);

  // Sync state
  const [syncInProgress, setSyncInProgress] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string>('');
  const [syncDays, setSyncDays] = useState(7);

  // Refs
  const tokenCreationInProgress = useRef<boolean>(false);
  const tokenRef = useRef<string | null>(null);
  const expiresAtRef = useRef<Date | null>(null);
  const appsPageRef = useRef<Awaited<ReturnType<FrontendClient["apps"]["list"]>> | null>(null);
  const connectSectionRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    tokenRef.current = token;
    expiresAtRef.current = expiresAt;
  }, [token, expiresAt]);

  useEffect(() => {
    // Only create client when we have a token for the first time
    if (!externalUserId || !token || pd) {
      return;
    }

    async function loadClient() {
      const { createFrontendClient } = await import('@pipedream/sdk/browser');
      const client = createFrontendClient({
        frontendHost,
        apiHost,
        externalUserId,
        token,
        tokenCallback: async () => {
          if (!externalUserId) {
            throw new Error("No external user ID provided");
          }

          const currentToken = tokenRef.current;
          const currentExpiresAt = expiresAtRef.current;
          if (currentToken && currentExpiresAt && currentExpiresAt > new Date()) {
            return {
              token: currentToken,
              expiresAt: currentExpiresAt,
            };
          }

          const res = await fetch("/api/pipedream/token", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ externalUserId }),
          });

          if (!res.ok) {
            throw new Error("Failed to refresh connect token");
          }

          const response = await res.json();
          const nextExpiresAt = ensureDate(response.expiresAt);
          setToken(response.token);
          setConnectLink(response.connectLinkUrl);
          setExpiresAt(nextExpiresAt);

          return {
            token: response.token,
            expiresAt: nextExpiresAt,
          };
        },
      });
      setPd(client);
    }

    loadClient();
  }, [externalUserId, token, pd]);

  const ensureDate = (value: Date | string): Date =>
    value instanceof Date ? value : new Date(value);

  interface ConnectResult {
    id: string
  }

  interface ConnectStatus {
    successful: boolean
    completed: boolean
  }

  interface ConnectConfig {
    app: string
    token?: string
    onSuccess: (result: ConnectResult) => void
    onError?: (error: Error) => void
    onClose?: (status: ConnectStatus) => void
  }

  const connectApp = async (appSlug: string) => {
    if (!externalUserId) {
      throw new Error("External user ID is required.");
    }
    if (!token) {
      throw new Error("Token is required.");
    }
    setAppSlug(appSlug)

    const connectConfig: ConnectConfig = {
      app: appSlug,
      token,
      onSuccess: async ({ id }: ConnectResult) => {
        console.log('🎉 Connection successful!', { accountId: id });
        setAccountId(id);

        // Save connection to Supabase database
        try {
          await fetch('http://localhost:8000/api/auth/save-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: externalUserId,
              external_user_id: externalUserId,
              account_id: id,
              app: appSlug
            })
          });
          console.log('✅ Connection saved to database');
          setStoredAccountId(id);
        } catch (error) {
          console.error('❌ Error saving connection:', error);
        }

        // Fetch account details to get the name
        try {
          const account = await getAccountById(id);
          setAccountName(account.name);
        } catch (error) {
          console.error('Error fetching account details:', error);
        }

        // Note: Token refresh is handled automatically by the SDK's tokenCallback
        // No need to manually create a new token here
      },
      onError: (error: Error) => {
        console.error('❌ Connection error:', error);
      },
      onClose: (status: ConnectStatus) => {
        console.log('🚪 Connection dialog closed:', {
          successful: status.successful,
          completed: status.completed
        });
      }
    }

    if (!pd) {
      console.error("Pipedream SDK not loaded")
      return
    }

    pd.connectAccount(connectConfig)
  }

  const connectAccount = async () => {
    if (!selectedApp) return
    await connectApp(selectedApp.data.nameSlug)
  }

  // Check for existing connection on mount
  const checkExistingConnection = async (userId: string) => {
    try {
      const response = await fetch(
        `http://localhost:8000/api/auth/check-connection?user_id=${userId}&app=gmail`
      );
      const data = await response.json();

      if (data.connected) {
        console.log('✅ Found existing connection:', data.account_id);
        setStoredAccountId(data.account_id);
        setAccountId(data.account_id);
        // Fetch account details to get the name
        try {
          const account = await getAccountById(data.account_id);
          setAccountName(account.name);
        } catch (error) {
          console.error('Error fetching account details:', error);
        }
      } else {
        console.log('ℹ️ No existing connection found');
      }
    } catch (error) {
      console.error('❌ Error checking connection:', error);
    } finally {
      setIsCheckingConnection(false);
    }
  };

  useEffect(() => {
    // Wait for auth to complete and user to be available
    if (authLoading || !user) return;

    // Prevent duplicate token creation (especially in React StrictMode)
    if (token || tokenCreationInProgress.current) return;

    tokenCreationInProgress.current = true;

    // Use Supabase user ID as the persistent external user ID
    const userId = user.id;
    setExternalUserId(userId);

    // Create token immediately after setting external user ID
    (async () => {
      try {
        console.log('Creating token for external user:', userId);
        const { token, connectLinkUrl, expiresAt: expiresAtValue } = await serverConnectTokenCreate({
          externalUserId: userId,
        })
        console.log('Token created successfully');
        setToken(token)
        setConnectLink(connectLinkUrl)
        setExpiresAt(ensureDate(expiresAtValue))

        // Check for existing connection after token is created
        await checkExistingConnection(userId);
      } catch (error) {
        console.error("Error creating token:", error)
      } finally {
        tokenCreationInProgress.current = false;
      }
    })()
  }, [authLoading, user, token]);

  // Check for existing connection when app is selected
  useEffect(() => {
    // Only run if we have all required data and an app is selected
    if (!selectedApp || !externalUserId || !user) return;

    // Only check for apps that require authentication
    const appSlug = selectedApp.data.nameSlug;
    if (appSlug === 'gmail') {
      setIsCheckingConnection(true);

      // Check for existing connection for this specific app
      (async () => {
        try {
          const response = await fetch(
            `http://localhost:8000/api/auth/check-connection?user_id=${externalUserId}&app=${appSlug}`
          );
          const data = await response.json();

          if (data.connected) {
            console.log('✅ Found existing connection for', appSlug, ':', data.account_id);
            setAccountId(data.account_id);
            setStoredAccountId(data.account_id);

            // Fetch account details to get the name
            try {
              const account = await getAccountById(data.account_id);
              setAccountName(account.name);
            } catch (error) {
              console.error('Error fetching account details:', error);
            }
          } else {
            console.log('ℹ️ No existing connection found for', appSlug);
            // Clear states if switching to an app without connection
            setAccountId(null);
            setStoredAccountId(null);
            setAccountName(null);
          }
        } catch (error) {
          console.error('❌ Error checking connection:', error);
        } finally {
          setIsCheckingConnection(false);
        }
      })();
    }
  }, [selectedApp, externalUserId, user]);

  const handleAppSlugChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setAppSlug(value);
    setError("");
    setSelectedIndex(-1); // Reset selection

    // Clear previous timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    if (value.length > 0) {
      setShowDropdown(true);
      setIsSearching(true);

      // Debounce search to avoid too many API calls
      const timeout = setTimeout(async () => {
        try {
          setCurrentQuery(value);
          appsPageRef.current = null; // Reset pagination for new search
          await searchAppsClient(value, 10);
        } catch (err) {
          console.error("Search error:", err);
          setSearchResults([]);
        } finally {
          setIsSearching(false);
        }
      }, 300); // 300ms debounce

      setSearchTimeout(timeout);
    } else {
      setShowDropdown(false);
      setSearchResults([]);
      setIsSearching(false);
      setCurrentQuery("");
      setHasMoreApps(true);
      appsPageRef.current = null;
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showDropdown || searchResults.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => prev < searchResults.length - 1 ? prev + 1 : 0);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => prev > 0 ? prev - 1 : searchResults.length - 1);
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && selectedIndex < searchResults.length) {
          handleAppSelect(searchResults[selectedIndex]);
        }
        break;
      case 'Escape':
        setShowDropdown(false);
        setSelectedIndex(-1);
        break;
    }
  }

  const searchAppsClient = useCallback(async (query?: string, limit: number = 10, append: boolean = false): Promise<App[]> => {
    if (!pd) {
      console.error("Pipedream client not loaded");
      return [];
    }

    console.log('Searching apps with SDK client', { query, limit, append });

    try {
      const pageLimit = limit * 2; // Request more to account for filtering

      if (!append) {
        appsPageRef.current = await pd.apps.list({
          q: query,
          limit: pageLimit,
          sortKey: "featured_weight",
          sortDirection: "desc",
        });
      } else {
        const page = appsPageRef.current;
        if (!page) {
          return [];
        }
        if (!page.hasNextPage()) {
          setHasMoreApps(false);
          return [];
        }
        await page.getNextPage();
      }

      const page = appsPageRef.current;
      if (!page) {
        return [];
      }

      const filteredApps = page.data.filter((app) => app.authType !== null);
      const limitedApps = filteredApps.slice(0, limit);

      setHasMoreApps(page.hasNextPage());

      if (append) {
        setSearchResults(prevResults => {
          const existingIds = new Set(prevResults.map(app => app.nameSlug));
          const newApps = limitedApps.filter(app => !existingIds.has(app.nameSlug));
          return [...prevResults, ...newApps];
        });
      } else {
        setSearchResults(limitedApps);
      }

      return limitedApps;
    } catch (error) {
      console.error("Error fetching apps:", error);
      if (!append) {
        setSearchResults([]);
        setHasMoreApps(false);
      }
      return [];
    }
  }, [pd]);

  const loadMoreApps = async () => {
    if (isLoadingMore || !hasMoreApps || !appsPageRef.current) return;

    setIsLoadingMore(true);
    try {
      // Load more apps with the current query
      await searchAppsClient(currentQuery, 10, true);
    } finally {
      setIsLoadingMore(false);
    }
  };

  const handleAppSlugFocus = async () => {
    // Load popular apps when user clicks into the input
    if (searchResults.length === 0) {
      setShowDropdown(true);
      setIsSearching(true);
      setCurrentQuery("");
      appsPageRef.current = null;

      try {
        await searchAppsClient(undefined, 10); // No query = popular apps
      } catch (err) {
        console.error("Search error:", err);
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    } else {
      setShowDropdown(true);
    }
  }

  const handleAppSelect = (app: App) => {
    setAppSlug(app.nameSlug);
    setShowDropdown(false);
    setError("");
    // Automatically submit the form when an app is selected
    handleSubmitWithApp(app);
  }

  const handleSubmitWithApp = async (app: App) => {
    try {
      // Create a mock GetAppResponse from the App data
      const mockResponse: GetAppResponse = {
        data: app
      };
      setSelectedApp(mockResponse);

      // Auto-scroll to Connect section after a brief delay
      setTimeout(() => {
        connectSectionRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }, 100);
    } catch (err) {
      console.error("Error:", err);
      setError(`Couldn't load the app ${app.nameSlug}`);
    }
  }

  // Set OAuth confirmed state when app changes
  useEffect(() => {
    setIsOAuthConfirmed(true);

    console.log('🔄 App changed effect:', {
      selectedApp: selectedApp?.data.nameSlug,
      storedAccountId,
      currentAccountId: accountId
    });

    // Only reset account info if we're switching away from an existing app
    // Don't reset if we're selecting an app for the first time or if it's the same app
    if (selectedApp && storedAccountId) {
      // Check if the newly selected app matches the stored connection
      // If user has Gmail stored and selects Gmail, keep the connection
      const isGmailApp = selectedApp.data.nameSlug === 'gmail';
      if (!isGmailApp) {
        // Switching to a different app - reset account info
        console.log('❌ Resetting accountId - different app selected');
        setAccountId(null);
        setAccountName(null);
      } else {
        console.log('✅ Preserving accountId for Gmail');
      }
    } else if (!selectedApp) {
      // Clearing app selection - reset everything
      console.log('❌ Resetting accountId - no app selected');
      setAccountId(null);
      setAccountName(null);
    }

    // Always reset messages and conversation history when switching apps
    setMessages([]);
    setConversationHistory([]);
  }, [selectedApp, storedAccountId, accountId]);

  // Fetch emails
  const handleFetchEmails = async () => {
    if (!externalUserId) return;

    setFetchingEmails(true);
    try {
      const response = await fetch(
        `http://localhost:8000/api/gmail/fetch?user_id=${externalUserId}&max_results=10`
      );
      const data = await response.json();

      setMessages([{
        role: 'assistant',
        content: `✅ Fetched and processed ${data.count} emails successfully! You can now ask questions about them.`
      }]);
    } catch {
      setMessages([{
        role: 'assistant',
        content: '❌ Failed to fetch emails. Please try again.'
      }]);
    } finally {
      setFetchingEmails(false);
    }
  };

  // Send message to agent
  const handleSendMessage = async () => {
    if (!input.trim() || !externalUserId) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/agent/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMessage,
          user_id: externalUserId,
          conversation_history: conversationHistory  // Send truncated history
        })
      });

      const data = await response.json();
      const assistantMessage = data.response;

      // Add assistant response to UI (with sources/facts_count for display)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: assistantMessage,
        sources: data.sources,
        facts_count: data.facts_count
      }]);

      // Update conversation history (keep only last 20 messages = 10 exchanges)
      // Strip sources/facts_count - only role and content for context
      setConversationHistory(prev => {
        const updated = [
          ...prev,
          { role: 'user', content: userMessage },
          { role: 'assistant', content: assistantMessage }
        ];
        // Keep only last 20 messages to prevent token overflow
        return updated.slice(-20);
      });
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '❌ Error querying knowledge graph. Please try again.'
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Handle sync
  const handleSync = async () => {
    if (!externalUserId || !accountId) {
      setSyncStatus('Error: Not connected to Gmail');
      return;
    }

    setSyncInProgress(true);
    setSyncStatus(`Starting ${syncDays}-day sync...`);

    try {
      const response = await fetch(
        `http://localhost:8000/api/gmail/sync-30-days?user_id=${externalUserId}&account_id=${accountId}&days=${syncDays}`,
        { method: 'POST' }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Sync failed');
      }

      const data = await response.json();

      if (data.status === 'success') {
        setSyncStatus(`✅ Synced ${data.total_processed} emails from last ${syncDays} days`);
      } else {
        setSyncStatus(`Error: ${data.message || 'Unknown error'}`);
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setSyncStatus(`❌ Sync failed: ${errorMessage}`);
      console.error('Sync error:', error);
    } finally {
      setSyncInProgress(false);
    }
  };

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.app-search-container')) {
        setShowDropdown(false);
        setSelectedIndex(-1);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Cleanup search timeout on unmount or timeout change
  useEffect(() => {
    return () => {
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }
    };
  }, [searchTimeout]);

  // Show loading state while auth is loading
  if (authLoading) {
    return (
      <main className="p-4 md:p-8 flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-lg text-gray-600">Loading...</div>
        </div>
      </main>
    );
  }

  // Show sign in screen if not authenticated
  if (!user) {
    return (
      <main className="p-4 md:p-8 flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center">
          <h1 className="text-3xl font-bold mb-6">Gmail Knowledge Graph Chat</h1>
          <p className="text-gray-600 mb-8">Sign in to access your personalized knowledge graph</p>
          <button
            onClick={signInWithGoogle}
            className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg"
          >
            Sign in with Google
          </button>
        </div>
      </main>
    );
  }

  // Show loading state while checking for existing connection
  if (isCheckingConnection) {
    return (
      <main className="p-4 md:p-8 flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-lg text-gray-600">Checking connection...</div>
        </div>
      </main>
    );
  }

  return (
    <main className="p-4 md:p-8 flex flex-col gap-6 max-w-4xl mx-auto w-full min-h-screen bg-gray-50">
      {/* Sign Out Button */}
      <button
        onClick={signOut}
        className="absolute top-4 right-4 px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded"
      >
        Sign Out
      </button>

      <h1 className="text-3xl font-bold">Gmail Knowledge Graph Chat</h1>

      {/* 1. Select App */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">1. Select App to Connect</h2>
        <ErrorBoundary>
          <div className="app-search-container relative max-w-md">
            <div className="flex gap-2">
              <div className="relative flex-1">
                {selectedApp ? (
                  <div className="shadow border rounded w-full px-3 py-2 bg-gray-50 border-gray-300 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <img
                        src={selectedApp.data.imgSrc}
                        alt={selectedApp.data.name}
                        className="w-6 h-6 rounded"
                      />
                      <div>
                        <div className="font-medium text-gray-900">{selectedApp.data.name}</div>
                        <div className="text-sm text-gray-500">{selectedApp.data.nameSlug}</div>
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedApp(null);
                        setAppSlug("");
                        setAccountId(null);
                        setAccountName(null);
                      }}
                      className="text-gray-400 hover:text-gray-600 p-1"
                      title="Clear selection"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      className="shadow appearance-none border rounded w-full px-3 py-2 pr-8 text-gray-700 leading-tight focus:outline-none focus:shadow-outline focus:border-blue-500"
                      id="app-slug"
                      type="text"
                      placeholder="Search apps (e.g., gmail, slack, google sheets)"
                      value={appSlug}
                      onChange={handleAppSlugChange}
                      onFocus={handleAppSlugFocus}
                      onKeyDown={handleKeyDown}
                      autoComplete="off"
                      role="combobox"
                      aria-expanded={showDropdown}
                      aria-haspopup="listbox"
                      aria-controls="app-dropdown"
                      aria-activedescendant={selectedIndex >= 0 ? `app-option-${selectedIndex}` : undefined}
                      aria-label="Search for apps to connect"
                    />
                    {appSlug && (
                      <button
                        onClick={() => {
                          setAppSlug("");
                          setSearchResults([]);
                          setShowDropdown(false);
                          setCurrentQuery("");
                          setHasMoreApps(true);
                          appsPageRef.current = null;
                        }}
                        className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 p-1"
                        title="Clear search"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                )}
                {showDropdown && (
                  <div
                    id="app-dropdown"
                    role="listbox"
                    className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-96 overflow-y-auto">
                    {isSearching ? (
                      <div className="px-4 py-2 text-gray-500">
                        Searching...
                      </div>
                    ) : searchResults.length > 0 ? (
                      searchResults.map((app, index) => (
                        <div
                          key={app.nameSlug}
                          id={`app-option-${index}`}
                          role="option"
                          aria-selected={index === selectedIndex}
                          className={`flex items-center px-4 py-3 cursor-pointer border-b border-gray-100 last:border-b-0 ${
                            index === selectedIndex ? 'bg-blue-100' : 'hover:bg-gray-100'
                          }`}
                          onClick={() => handleAppSelect(app)}
                        >
                          <img
                            src={app.imgSrc}
                            alt={app.name}
                            className="w-8 h-8 rounded mr-3 object-contain"
                            onError={(e) => {
                              const target = e.target as HTMLImageElement;
                              target.style.display = 'none';
                            }}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-gray-900 truncate">
                              <span>{app.name}</span>
                              <code className="text-sm font-normal text-gray-500 truncate">{' ('}{app.nameSlug}{')'}</code>
                            </div>
                            {app.description && (
                              <div className="text-sm text-gray-400 mt-1 line-clamp-2">{app.description}</div>
                            )}
                          </div>
                          <div className="text-xs text-gray-400 ml-2">
                            {app.authType === 'oauth' ? 'OAuth' :
                             app.authType === 'keys' ? 'API Keys' :
                             'No Auth'}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="px-4 py-2 text-gray-500">
                        No apps found
                      </div>
                    )}
                    {!isSearching && searchResults.length > 0 && hasMoreApps && (
                      <div className="border-t border-gray-100">
                        <button
                          onClick={loadMoreApps}
                          disabled={isLoadingMore}
                          className="w-full px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 focus:outline-none focus:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isLoadingMore ? 'Loading...' : 'Load more'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
          {error && <p className="text-red-600 mt-2">{error}</p>}
        </ErrorBoundary>
      </div>

      {/* 2. Connect & Fetch */}
      {selectedApp && (
        <div className="bg-white rounded-lg shadow p-6" ref={connectSectionRef}>
          <h2 className="text-xl font-semibold mb-4">2. Connect & Fetch Emails</h2>

          {accountId ? (
            <>
              <div className="p-3 bg-green-100 border border-green-400 text-green-700 rounded mb-4">
                ✅ Account connected! {accountName && <><strong>{accountName}</strong> (ID: <code className="font-mono text-sm">{accountId}</code>)</>}
              </div>

              {selectedApp?.data.nameSlug === 'gmail' && (
                <div className="mt-4 space-y-4">
                  {/* Testing Tools Section */}
                  <div className="flex gap-4">
                    {/* Fetch 10 Emails Button */}
                    <button
                      onClick={handleFetchEmails}
                      disabled={fetchingEmails}
                      className={`px-6 py-3 rounded-lg font-medium ${
                        fetchingEmails
                          ? 'bg-gray-400 cursor-not-allowed text-gray-700'
                          : 'bg-green-600 hover:bg-green-700 text-white'
                      }`}
                    >
                      {fetchingEmails ? 'Fetching...' : 'Fetch My Last 10 Emails'}
                    </button>

                    {/* Sync Button with Dropdown */}
                    <div className="flex gap-2">
                      <select
                        value={syncDays}
                        onChange={(e) => setSyncDays(Number(e.target.value))}
                        disabled={syncInProgress}
                        className="px-3 py-2 border border-gray-300 rounded-lg"
                      >
                        <option value={7}>7 days</option>
                        <option value={14}>14 days</option>
                        <option value={30}>30 days</option>
                        <option value={90}>90 days</option>
                      </select>

                      <button
                        onClick={handleSync}
                        disabled={syncInProgress}
                        className={`px-6 py-3 rounded-lg font-medium ${
                          syncInProgress
                            ? 'bg-gray-400 cursor-not-allowed text-gray-700'
                            : 'bg-blue-600 hover:bg-blue-700 text-white'
                        }`}
                      >
                        {syncInProgress ? 'Syncing...' : `Sync Last ${syncDays} Days`}
                      </button>
                    </div>
                  </div>

                  {/* Status Messages */}
                  {syncStatus && (
                    <p className="text-sm text-gray-700">{syncStatus}</p>
                  )}

                  <p className="text-xs text-gray-500">
                    ⚠️ Keep window open during sync. Closes if you navigate away.
                  </p>
                </div>
              )}
            </>
          ) : (
            <button
              className="bg-blue-500 hover:bg-blue-700 text-white py-2 px-4 rounded"
              onClick={connectAccount}
            >
              Connect {selectedApp.data.name}
            </button>
          )}
        </div>
      )}

      {/* 3. Chat Interface */}
      {selectedApp?.data.nameSlug === 'gmail' && accountId && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">3. Ask Questions</h2>

          {/* Messages */}
          <div className="h-96 overflow-y-auto mb-4 border rounded p-4 bg-gray-50">
            {messages.length === 0 ? (
              <div className="text-gray-500">
                <p className="mb-2">Fetch emails first, then try asking:</p>
                <ul className="list-disc list-inside space-y-1 text-sm">
                  <li>&quot;Who emailed me?&quot;</li>
                  <li>&quot;What emails did I get about proposals?&quot;</li>
                  <li>&quot;Summarize my recent emails&quot;</li>
                </ul>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} className={`mb-4 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                  <div className={`inline-block p-3 rounded-lg max-w-[80%] ${
                    msg.role === 'user'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-900'
                  }`}>
                    {msg.content}
                  </div>
                  {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2 text-left">
                      <details className="text-xs text-gray-600">
                        <summary className="cursor-pointer hover:text-gray-800">
                          📚 {msg.facts_count} facts found • View {msg.sources.length} sources
                        </summary>
                        <ul className="mt-2 space-y-1 pl-4">
                          {msg.sources.map((source, idx) => (
                            <li key={idx} className="text-gray-700">• {source}</li>
                          ))}
                        </ul>
                      </details>
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !loading && handleSendMessage()}
              placeholder="Ask about your emails..."
              className="flex-1 p-2 border rounded focus:outline-none focus:border-blue-500"
              disabled={loading}
            />
            <button
              onClick={handleSendMessage}
              disabled={loading || !input.trim()}
              className="bg-green-500 hover:bg-green-700 text-white py-2 px-6 rounded disabled:opacity-50"
            >
              {loading ? 'Thinking...' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
