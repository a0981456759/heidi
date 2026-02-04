/**
 * Heidi Calls: Intelligent Voicemail Dashboard
 * Warm, calm interface for medical administrators
 * Enhanced with Emergency Escalation UI for Level 5 cases
 */

import React, { useState, useEffect, useMemo } from 'react';

// ============================================================================
// API FUNCTIONS
// ============================================================================
// Use environment variable for production, fallback to proxy path for local dev
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

const api = {
  fetchVoicemails: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`${API_BASE}/voicemail/${query ? '?' + query : ''}`);
    if (!res.ok) throw new Error('Failed to fetch voicemails');
    return res.json();
  },

  updateVoicemail: async (id, data) => {
    const res = await fetch(`${API_BASE}/voicemail/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update voicemail');
    return res.json();
  },

  // Callback Tracking
  recordCallback: async (id, status, by, notes = null) => {
    const res = await fetch(`${API_BASE}/voicemail/${id}/callback?callback_status=${status}&callback_by=${encodeURIComponent(by)}${notes ? '&notes=' + encodeURIComponent(notes) : ''}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to record callback');
    return res.json();
  },

  // Escalation
  acknowledgeEscalation: async (id, by) => {
    const res = await fetch(`${API_BASE}/voicemail/${id}/acknowledge-escalation?acknowledged_by=${encodeURIComponent(by)}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to acknowledge');
    return res.json();
  },

  getActiveEscalations: async () => {
    const res = await fetch(`${API_BASE}/voicemail/escalations/active`);
    if (!res.ok) throw new Error('Failed to fetch escalations');
    return res.json();
  },

  // PMS Integration
  searchPMSPatient: async (system, phone) => {
    const res = await fetch(`${API_BASE}/voicemail/pms/search?pms_system=${system}&phone=${phone}`);
    if (!res.ok) throw new Error('Failed to search PMS');
    return res.json();
  },

  linkToPMS: async (id, system, patientId) => {
    const res = await fetch(`${API_BASE}/voicemail/${id}/link-pms?pms_system=${system}&pms_patient_id=${patientId}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to link to PMS');
    return res.json();
  },

  // Duplicates
  getDuplicateSummary: async () => {
    const res = await fetch(`${API_BASE}/voicemail/duplicates/summary`);
    if (!res.ok) throw new Error('Failed to fetch duplicates');
    return res.json();
  },
};

// ============================================================================
// OFFLINE MODE - Service Worker & Local Storage
// ============================================================================
const offlineStorage = {
  // Save voicemails to local storage for offline access
  saveVoicemails: (voicemails) => {
    try {
      localStorage.setItem('heidi_voicemails_cache', JSON.stringify({
        data: voicemails,
        timestamp: Date.now()
      }));
    } catch (e) {
      console.warn('Failed to cache voicemails:', e);
    }
  },

  // Get cached voicemails
  getVoicemails: () => {
    try {
      const cached = localStorage.getItem('heidi_voicemails_cache');
      if (cached) {
        const { data, timestamp } = JSON.parse(cached);
        // Cache valid for 1 hour
        if (Date.now() - timestamp < 3600000) {
          return data;
        }
      }
    } catch (e) {
      console.warn('Failed to read cache:', e);
    }
    return null;
  },

  // Queue offline actions for sync
  queueAction: (action) => {
    try {
      const queue = JSON.parse(localStorage.getItem('heidi_offline_queue') || '[]');
      queue.push({ ...action, timestamp: Date.now() });
      localStorage.setItem('heidi_offline_queue', JSON.stringify(queue));
    } catch (e) {
      console.warn('Failed to queue action:', e);
    }
  },

  // Get pending actions
  getPendingActions: () => {
    try {
      return JSON.parse(localStorage.getItem('heidi_offline_queue') || '[]');
    } catch (e) {
      return [];
    }
  },

  // Clear synced actions
  clearActions: () => {
    localStorage.removeItem('heidi_offline_queue');
  }
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================
const formatTime = (isoString) => {
  const date = new Date(isoString);
  return date.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' });
};

const formatDate = (isoString) => {
  const date = new Date(isoString);
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  if (isToday) return 'Today';
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
};

const getTimeSince = (isoString) => {
  const now = new Date();
  const date = new Date(isoString);
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
};

// Get waiting time with SLA status
const getWaitingTimeWithSLA = (isoString, urgencyLevel) => {
  const now = new Date();
  const date = new Date(isoString);
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);

  // SLA targets by urgency level (in minutes)
  const slaTargets = {
    5: 5,     // Critical: 5 min
    4: 120,   // High: 2 hours
    3: 480,   // Standard: 8 hours (same day)
    2: 1440,  // Moderate: 24 hours
    1: 2880,  // Low: 48 hours
  };

  const slaMinutes = slaTargets[urgencyLevel] || 480;
  const isBreached = diffMins > slaMinutes;
  const isWarning = diffMins > slaMinutes * 0.75;

  let timeText;
  if (diffMins < 60) {
    timeText = `${diffMins}m`;
  } else if (diffHours < 24) {
    timeText = `${diffHours}h ${diffMins % 60}m`;
  } else {
    const diffDays = Math.floor(diffHours / 24);
    timeText = `${diffDays}d ${diffHours % 24}h`;
  }

  return {
    text: timeText,
    isBreached,
    isWarning,
    slaText: urgencyLevel >= 4 ? `SLA: ${slaMinutes < 60 ? slaMinutes + 'm' : Math.floor(slaMinutes / 60) + 'h'}` : null
  };
};

const getUrgencyConfig = (level, isAmbiguous = false) => {
  if (isAmbiguous) {
    return { label: 'Review', color: '#6B7280', bgColor: '#F3F4F6', accentColor: '#9CA3AF', textColor: '#4B5563' };
  }
  const configs = {
    5: { label: 'Critical', color: '#DC2626', bgColor: '#FEE2E2', accentColor: '#DC2626', textColor: '#991B1B' },
    4: { label: 'High', color: '#EA580C', bgColor: '#FFEDD5', accentColor: '#EA580C', textColor: '#9A3412' },
    3: { label: 'Standard', color: '#78716C', bgColor: '#F5F5F4', accentColor: '#A8A29E', textColor: '#57534E' },
    2: { label: 'Low', color: '#78716C', bgColor: '#FAFAF9', accentColor: '#D6D3D1', textColor: '#78716C' },
    1: { label: 'Info', color: '#A1A1AA', bgColor: '#FAFAFA', accentColor: '#E4E4E7', textColor: '#A1A1AA' },
  };
  return configs[level] || configs[3];
};

const getIntentConfig = (intent) => {
  const configs = {
    Emergency: { icon: '🚨', label: 'Emergency', color: '#DC2626' },
    Prescription: { icon: '💊', label: 'Prescription', color: '#7C3AED' },
    Results: { icon: '📋', label: 'Results', color: '#2563EB' },
    Booking: { icon: '📅', label: 'Booking', color: '#059669' },
    Billing: { icon: '💳', label: 'Billing', color: '#D97706' },
    Referral: { icon: '🔄', label: 'Referral', color: '#0891B2' },
    Ambiguous: { icon: '⚠️', label: 'Needs Review', color: '#6B7280' },
    Other: { icon: '📝', label: 'Other', color: '#6B7280' },
  };
  return configs[intent] || configs.Other;
};

const getStatusConfig = (status) => {
  const configs = {
    pending: { label: 'Pending', color: '#D97706', bgColor: '#FEF3C7' },
    processed: { label: 'Processed', color: '#2563EB', bgColor: '#DBEAFE' },
    actioned: { label: 'Actioned', color: '#059669', bgColor: '#D1FAE5' },
    archived: { label: 'Archived', color: '#6B7280', bgColor: '#F3F4F6' },
  };
  return configs[status] || configs.pending;
};

// Location display config
const getLocationConfig = (locationId) => {
  const configs = {
    harbour: { label: 'Harbour', color: '#0284C7', bgColor: '#E0F2FE', icon: '🏥' },
    sunset: { label: 'Sunset', color: '#EA580C', bgColor: '#FFEDD5', icon: '🌅' },
    central: { label: 'Central', color: '#7C3AED', bgColor: '#EDE9FE', icon: '🏛️' },
    northside: { label: 'Northside', color: '#059669', bgColor: '#D1FAE5', icon: '🧭' },
  };
  return configs[locationId] || { label: locationId, color: '#6B7280', bgColor: '#F3F4F6', icon: '📍' };
};

// Mask phone number for privacy
const maskPhone = (phone) => {
  if (!phone) return null;
  const last3 = phone.slice(-3);
  return `•••••••${last3}`;
};

// Parse transcript with uncertainty markers
// Format: {{heard??alternatives}} e.g., {{heving??having}}
const parseUncertainTranscript = (transcript) => {
  if (!transcript) return [];

  const regex = /\{\{([^?]+)\?\?([^}]+)\}\}/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(transcript)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      parts.push({
        type: 'clear',
        text: transcript.slice(lastIndex, match.index)
      });
    }

    // Add the uncertain part
    parts.push({
      type: 'uncertain',
      heard: match[1],
      alternatives: match[2].split('/')
    });

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < transcript.length) {
    parts.push({
      type: 'clear',
      text: transcript.slice(lastIndex)
    });
  }

  return parts;
};

// Render transcript with highlighted uncertain parts
const TranscriptWithUncertainty = ({ transcript, onPlayWord }) => {
  const parts = parseUncertainTranscript(transcript);
  const hasUncertainParts = parts.some(p => p.type === 'uncertain');

  if (!hasUncertainParts) {
    return <span>{transcript}</span>;
  }

  return (
    <span>
      {parts.map((part, index) => {
        if (part.type === 'clear') {
          return <span key={index}>{part.text}</span>;
        }

        return (
          <span
            key={index}
            className="relative inline-block group"
          >
            <span
              className="bg-amber-200 text-amber-900 px-1 py-0.5 rounded cursor-help border-b-2 border-amber-400 border-dashed"
              title={`Alternatives: ${part.alternatives.join(' / ')}`}
            >
              {part.heard}
              <span className="text-[9px] text-amber-600 ml-0.5">?</span>
            </span>
            {/* Tooltip */}
            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-stone-800 text-white text-[10px] rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
              Could be: {part.alternatives.join(' / ')}
            </span>
          </span>
        );
      })}
    </span>
  );
};

// Legend for transcript markers
const TranscriptLegend = () => (
  <div className="flex items-center gap-4 text-[10px] text-stone-500 mt-2 pt-2 border-t border-stone-100">
    <div className="flex items-center gap-1">
      <span className="bg-amber-200 text-amber-900 px-1 rounded text-[9px]">word?</span>
      <span>= Uncertain (hover for alternatives)</span>
    </div>
  </div>
);

// Text-to-Speech for emergency script
const speakEmergencyScript = (script) => {
  if ('speechSynthesis' in window) {
    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    // Split by language sections and speak
    const englishMatch = script.match(/\[ENGLISH\]\s*([\s\S]*?)\s*\[中文\]/);
    const textToSpeak = englishMatch ? englishMatch[1].trim() : script;

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.rate = 0.9;
    utterance.pitch = 1;
    utterance.lang = 'en-AU';

    window.speechSynthesis.speak(utterance);
  } else {
    alert('Text-to-speech not supported in this browser');
  }
};

// ============================================================================
// TOAST NOTIFICATION SYSTEM
// ============================================================================
const ToastContext = React.createContext();

const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3000);
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {/* Toast Container */}
      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`
              px-4 py-3 rounded-lg shadow-lg text-sm font-medium flex items-center gap-2
              animate-slide-in
              ${toast.type === 'success' ? 'bg-emerald-600 text-white' : ''}
              ${toast.type === 'error' ? 'bg-red-600 text-white' : ''}
              ${toast.type === 'info' ? 'bg-blue-600 text-white' : ''}
            `}
          >
            {toast.type === 'success' && '✓'}
            {toast.type === 'error' && '✕'}
            {toast.type === 'info' && 'ℹ'}
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

const useToast = () => React.useContext(ToastContext);

// ============================================================================
// COMPONENTS
// ============================================================================

// Privacy-aware Phone Button with Click-to-Call
const PhoneButton = ({ phone, phoneMasked }) => {
  const [revealed, setRevealed] = useState(false);

  if (!phone) return null;

  const displayPhone = revealed ? phone : (phoneMasked || maskPhone(phone));

  return (
    <div className="flex items-center gap-2">
      <a
        href={`tel:${phone}`}
        className="inline-flex items-center gap-2 px-3 py-2 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg text-emerald-700 font-medium text-sm transition-colors"
        onClick={(e) => e.stopPropagation()}
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
        </svg>
        <span className="font-mono">{displayPhone}</span>
      </a>
      <button
        onClick={(e) => { e.stopPropagation(); setRevealed(!revealed); }}
        className="p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded transition-colors"
        title={revealed ? 'Hide number' : 'Show full number'}
      >
        {revealed ? '🙈' : '👁️'}
      </button>
    </div>
  );
};

// Confidence Indicator
const ConfidenceIndicator = ({ confidence }) => {
  const percentage = Math.round(confidence * 100);
  const isLow = confidence < 0.6;

  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-stone-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${isLow ? 'bg-amber-400' : 'bg-emerald-400'}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className={`text-xs font-mono ${isLow ? 'text-amber-600' : 'text-stone-400'}`}>
        {percentage}%
      </span>
    </div>
  );
};

// Location Badge
const LocationBadge = ({ locationInfo }) => {
  if (!locationInfo?.assigned_location) return null;

  const config = getLocationConfig(locationInfo.assigned_location);

  return (
    <span
      className="text-[10px] font-medium px-1.5 py-0.5 rounded flex items-center gap-1"
      style={{ color: config.color, backgroundColor: config.bgColor }}
      title={`Routing: ${locationInfo.routing_reason}`}
    >
      {config.icon} @{config.label}
    </span>
  );
};

// Patient Match Badge
const PatientMatchBadge = ({ patientMatch, medicareNumber }) => {
  if (!patientMatch) return null;

  return (
    <div className="flex items-center gap-2">
      {patientMatch.medicare_matched ? (
        <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded flex items-center gap-1">
          ✅ Medicare Matched
        </span>
      ) : medicareNumber ? (
        <span className="text-[10px] px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded flex items-center gap-1">
          ⚠️ Medicare Unmatched
        </span>
      ) : null}
      {medicareNumber && (
        <span className="text-[10px] font-mono text-stone-400">
          {medicareNumber}
        </span>
      )}
    </div>
  );
};

// Medicare Privacy Toggle - Click to reveal full number
const MedicareDisplay = ({ masked, full }) => {
  const [revealed, setRevealed] = useState(false);

  if (!masked && !full) return null;

  const displayValue = revealed ? full : masked;

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-mono text-stone-400 bg-stone-50 px-1.5 py-0.5 rounded">
        {displayValue || masked}
      </span>
      {full && (
        <button
          onClick={(e) => { e.stopPropagation(); setRevealed(!revealed); }}
          className="p-0.5 text-stone-400 hover:text-stone-600 transition-colors"
          title={revealed ? 'Hide Medicare' : 'Reveal Medicare'}
        >
          {revealed ? '🔒' : '🔓'}
        </button>
      )}
    </div>
  );
};

// Doctor Mentioned Badge
const DoctorBadge = ({ doctorName }) => {
  if (!doctorName) return null;

  return (
    <span className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded flex items-center gap-1">
      👨‍⚕️ {doctorName}
    </span>
  );
};

// Emergency Escalation Status Banner
const EscalationBanner = ({ escalation }) => {
  if (!escalation?.escalation_triggered) return null;

  return (
    <div className="bg-red-50 border-b border-red-200 px-3 py-2">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs font-semibold text-red-700 uppercase tracking-wide flex items-center gap-1">
          <span className="inline-block w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
          Emergency Escalation Active
        </span>
        <div className="flex items-center gap-2">
          {escalation.actions_taken?.includes('Voice_Alert_Sent_To_Patient') && (
            <span className="text-[10px] px-2 py-0.5 bg-red-100 text-red-700 rounded-full flex items-center gap-1">
              📞 Voice Alert Sent (Call 000)
            </span>
          )}
          {escalation.actions_taken?.includes('SMS_Alert_Sent_To_Manager') && (
            <span className="text-[10px] px-2 py-0.5 bg-red-100 text-red-700 rounded-full flex items-center gap-1">
              📱 SMS Sent to Manager
            </span>
          )}
        </div>
        {escalation.timestamp_escalated && (
          <span className="text-[10px] text-red-400 ml-auto">
            Escalated: {new Date(escalation.timestamp_escalated).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  );
};

// Listen to Automated Reply Button
const ListenButton = ({ script }) => {
  const [isPlaying, setIsPlaying] = useState(false);

  const handleListen = (e) => {
    e.stopPropagation();
    if (isPlaying) {
      window.speechSynthesis.cancel();
      setIsPlaying(false);
    } else {
      setIsPlaying(true);
      speakEmergencyScript(script);

      // Reset playing state when speech ends
      const checkSpeaking = setInterval(() => {
        if (!window.speechSynthesis.speaking) {
          setIsPlaying(false);
          clearInterval(checkSpeaking);
        }
      }, 100);
    }
  };

  return (
    <button
      onClick={handleListen}
      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 ${isPlaying
          ? 'bg-red-100 text-red-700 border border-red-200'
          : 'bg-stone-100 hover:bg-stone-200 text-stone-600 border border-stone-200'
        }`}
    >
      {isPlaying ? '⏹️ Stop' : '🔊 Listen to Automated Reply'}
    </button>
  );
};

// Audio Player for Original Voicemail Recording
// Simulates different accents using TTS voice settings
const VoicemailAudioPlayer = ({ audioUrl, transcript, voicemailId, languageCode, isAccentCase }) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [availableVoices, setAvailableVoices] = useState([]);

  // Load available voices
  React.useEffect(() => {
    const loadVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      setAvailableVoices(voices);
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }, []);

  // Find a voice that matches the accent simulation
  const getVoiceForAccent = (code) => {
    // Try to find voices for accent simulation
    const voicePreferences = {
      'en-AU': ['en-AU', 'en-GB', 'en'],  // Australian
      'en-IN': ['en-IN', 'hi-IN', 'en'],   // Indian accent
      'en-GB': ['en-GB', 'en-AU', 'en'],   // British
      'en': ['en-US', 'en-GB', 'en'],
    };

    const prefs = voicePreferences[code] || voicePreferences['en'];

    for (const pref of prefs) {
      const voice = availableVoices.find(v => v.lang.startsWith(pref));
      if (voice) return voice;
    }
    return availableVoices[0];
  };

  const handlePlay = (e) => {
    e.stopPropagation();

    if (isPlaying) {
      window.speechSynthesis.cancel();
      setIsPlaying(false);
      return;
    }

    setIsPlaying(true);
    const utterance = new SpeechSynthesisUtterance(transcript);

    // Configure TTS based on accent type
    if (isAccentCase) {
      // Simulate accent with adjusted parameters
      const voice = getVoiceForAccent(languageCode || 'en');
      if (voice) utterance.voice = voice;

      // Adjust for accent simulation
      if (languageCode === 'en-AU') {
        // Australian: slightly faster, higher pitch
        utterance.rate = 1.05;
        utterance.pitch = 1.1;
      } else {
        // Indian/other heavy accent: slower, varied pitch
        utterance.rate = 0.85;
        utterance.pitch = 1.15;
      }
    } else {
      utterance.rate = 0.95;
      utterance.pitch = 1.0;
    }

    utterance.lang = languageCode || 'en-AU';
    utterance.onend = () => setIsPlaying(false);
    utterance.onerror = () => setIsPlaying(false);

    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handlePlay}
        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 ${isPlaying
            ? 'bg-blue-100 text-blue-700 border border-blue-200'
            : isAccentCase
              ? 'bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200'
              : 'bg-stone-50 hover:bg-stone-100 text-stone-600 border border-stone-200'
          }`}
        title="Listen to voicemail (TTS simulation)"
      >
        {isPlaying ? (
          <>
            <span className="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
            Stop
          </>
        ) : (
          <>
            🎧 {isAccentCase ? 'Listen (Accent Demo)' : 'Listen to Recording'}
          </>
        )}
      </button>
      <span className="text-[10px] text-stone-400">
        {isAccentCase ? 'TTS accent simulation' : 'TTS playback'}
      </span>
    </div>
  );
};

// ============================================================================
// ADVANCED FEATURE COMPONENTS
// ============================================================================

// Repeat Caller Badge - Shows when patient has called multiple times
const RepeatCallerBadge = ({ callCount, isRepeatCaller, relatedIds }) => {
  if (!isRepeatCaller && callCount <= 1) return null;

  return (
    <span
      className="text-[10px] px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded flex items-center gap-1"
      title={relatedIds?.length > 0 ? `Related voicemails: ${relatedIds.join(', ')}` : 'Multiple calls detected'}
    >
      <span className="inline-block w-1.5 h-1.5 bg-purple-500 rounded-full"></span>
      Called {callCount}x today
    </span>
  );
};

// Callback Status Badge
const CallbackStatusBadge = ({ status }) => {
  if (!status || status === 'pending') return null;

  const configs = {
    attempted: { label: 'Callback Attempted', color: '#D97706', bgColor: '#FEF3C7', icon: '📞' },
    successful: { label: 'Called Back', color: '#059669', bgColor: '#D1FAE5', icon: '✓' },
    no_answer: { label: 'No Answer', color: '#DC2626', bgColor: '#FEE2E2', icon: '✗' },
    left_message: { label: 'Left Message', color: '#2563EB', bgColor: '#DBEAFE', icon: '💬' },
    wrong_number: { label: 'Wrong Number', color: '#6B7280', bgColor: '#F3F4F6', icon: '⚠️' },
  };

  const config = configs[status] || configs.attempted;

  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1"
      style={{ color: config.color, backgroundColor: config.bgColor }}
    >
      {config.icon} {config.label}
    </span>
  );
};

// Callback Tracking Panel - Record callback status
const CallbackTrackingPanel = ({ voicemail, onCallbackRecorded }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState('');
  const [notes, setNotes] = useState('');
  const [staffName, setStaffName] = useState('');
  const toast = useToast();

  const handleRecord = async () => {
    if (!selectedStatus || !staffName) {
      toast?.addToast('Please select status and enter your name', 'error');
      return;
    }

    try {
      const updated = await api.recordCallback(voicemail.voicemail_id, selectedStatus, staffName, notes || null);
      onCallbackRecorded(updated);
      toast?.addToast('Callback recorded successfully', 'success');
      setIsRecording(false);
      setSelectedStatus('');
      setNotes('');
    } catch (err) {
      toast?.addToast('Failed to record callback', 'error');
    }
  };

  if (voicemail.callback_status === 'successful') {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
        <div className="flex items-center gap-2 text-emerald-700">
          <span className="text-lg">✓</span>
          <div>
            <p className="text-xs font-medium">Callback Completed</p>
            <p className="text-[11px] text-emerald-600">
              By {voicemail.callback_by} on {voicemail.callback_completed_at ? new Date(voicemail.callback_completed_at).toLocaleString('en-AU') : 'N/A'}
            </p>
            {voicemail.callback_notes && (
              <p className="text-[11px] text-emerald-600 mt-1 italic">"{voicemail.callback_notes}"</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (!isRecording) {
    return (
      <button
        onClick={(e) => { e.stopPropagation(); setIsRecording(true); }}
        className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-medium rounded-lg transition-colors flex items-center gap-1.5 border border-blue-200"
      >
        📞 Record Callback
      </button>
    );
  }

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-3" onClick={(e) => e.stopPropagation()}>
      <h4 className="text-xs font-medium text-blue-800">Record Callback Outcome</h4>

      <div className="grid grid-cols-2 gap-2">
        {[
          { value: 'successful', label: 'Successful', icon: '✓' },
          { value: 'no_answer', label: 'No Answer', icon: '✗' },
          { value: 'left_message', label: 'Left Message', icon: '💬' },
          { value: 'wrong_number', label: 'Wrong Number', icon: '⚠️' },
        ].map((option) => (
          <button
            key={option.value}
            onClick={() => setSelectedStatus(option.value)}
            className={`px-2 py-1.5 text-[11px] rounded border transition-colors flex items-center gap-1 ${selectedStatus === option.value
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-stone-700 border-stone-200 hover:border-blue-300'
              }`}
          >
            {option.icon} {option.label}
          </button>
        ))}
      </div>

      <input
        type="text"
        placeholder="Your name"
        value={staffName}
        onChange={(e) => setStaffName(e.target.value)}
        className="w-full px-2 py-1.5 text-xs border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-300"
      />

      <textarea
        placeholder="Notes (optional)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={2}
        className="w-full px-2 py-1.5 text-xs border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-300"
      />

      <div className="flex items-center gap-2">
        <button
          onClick={handleRecord}
          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded transition-colors"
        >
          Save
        </button>
        <button
          onClick={() => setIsRecording(false)}
          className="px-3 py-1.5 bg-white hover:bg-stone-50 text-stone-600 text-xs rounded border border-stone-200 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
};

// Escalation Timeout Alert - Pulsing alert for unacknowledged Level 5 cases
const EscalationTimeoutAlert = ({ voicemail, onAcknowledge }) => {
  const [staffName, setStaffName] = useState('');
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const toast = useToast();

  const hasEscalation = voicemail.escalation?.escalation_triggered;
  const isAcknowledged = voicemail.escalation_acknowledged;

  if (!hasEscalation || isAcknowledged) return null;

  // Calculate time since escalation
  const escalatedAt = voicemail.escalation?.timestamp_escalated;
  const minutesSince = escalatedAt
    ? Math.floor((Date.now() - new Date(escalatedAt).getTime()) / 60000)
    : 0;

  const handleAcknowledge = async () => {
    if (!staffName) {
      toast?.addToast('Please enter your name', 'error');
      return;
    }

    try {
      const updated = await api.acknowledgeEscalation(voicemail.voicemail_id, staffName);
      onAcknowledge(updated);
      toast?.addToast('Escalation acknowledged', 'success');
      setIsAcknowledging(false);
    } catch (err) {
      toast?.addToast('Failed to acknowledge', 'error');
    }
  };

  return (
    <div className="bg-red-100 border-2 border-red-400 rounded-lg p-3 animate-pulse" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🚨</span>
          <div>
            <p className="text-sm font-bold text-red-800">UNACKNOWLEDGED EMERGENCY</p>
            <p className="text-[11px] text-red-700">
              Escalated {minutesSince} min ago
              {voicemail.escalation_reminder_count > 0 && ` • ${voicemail.escalation_reminder_count} reminder(s) sent`}
            </p>
          </div>
        </div>

        {!isAcknowledging ? (
          <button
            onClick={() => setIsAcknowledging(true)}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-bold rounded-lg transition-colors shadow-lg"
          >
            ACKNOWLEDGE
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Your name"
              value={staffName}
              onChange={(e) => setStaffName(e.target.value)}
              className="px-2 py-1.5 text-xs border border-red-300 rounded focus:outline-none focus:ring-1 focus:ring-red-400 w-32"
            />
            <button
              onClick={handleAcknowledge}
              className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded transition-colors"
            >
              Confirm
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// PMS Link Panel - Search and link to Practice Management System
const PMSLinkPanel = ({ voicemail, onPMSLinked }) => {
  const [isLinking, setIsLinking] = useState(false);
  const [selectedSystem, setSelectedSystem] = useState('best_practice');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const toast = useToast();

  const handleSearch = async () => {
    const phone = voicemail.extracted_entities?.callback_number || voicemail.caller_phone_redacted;
    if (!phone) {
      toast?.addToast('No phone number available for search', 'error');
      return;
    }

    try {
      setIsSearching(true);
      const results = await api.searchPMSPatient(selectedSystem, phone);
      setSearchResults(results.results || []);
      if (results.results?.length === 0) {
        toast?.addToast('No matching patients found', 'info');
      }
    } catch (err) {
      toast?.addToast('Failed to search PMS', 'error');
    } finally {
      setIsSearching(false);
    }
  };

  const handleLink = async (patientId) => {
    try {
      const updated = await api.linkToPMS(voicemail.voicemail_id, selectedSystem, patientId);
      onPMSLinked(updated);
      toast?.addToast('Linked to PMS patient', 'success');
      setIsLinking(false);
    } catch (err) {
      toast?.addToast('Failed to link to PMS', 'error');
    }
  };

  // If already linked
  if (voicemail.pms_linked) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded flex items-center gap-1">
          ✓ PMS Linked
        </span>
        <span className="text-[10px] text-stone-400">
          {voicemail.pms_system?.replace('_', ' ')} #{voicemail.pms_patient_id}
        </span>
      </div>
    );
  }

  if (!isLinking) {
    return (
      <button
        onClick={(e) => { e.stopPropagation(); setIsLinking(true); }}
        className="text-[10px] px-1.5 py-0.5 bg-stone-100 hover:bg-stone-200 text-stone-600 rounded flex items-center gap-1 transition-colors"
      >
        🔗 Link to PMS
      </button>
    );
  }

  return (
    <div className="bg-stone-50 border border-stone-200 rounded-lg p-3 space-y-3" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-stone-700">Link to Practice Management System</h4>
        <button
          onClick={() => setIsLinking(false)}
          className="text-stone-400 hover:text-stone-600"
        >
          ✕
        </button>
      </div>

      <div className="flex items-center gap-2">
        <select
          value={selectedSystem}
          onChange={(e) => setSelectedSystem(e.target.value)}
          className="px-2 py-1.5 text-xs border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-amber-300"
        >
          <option value="best_practice">Best Practice</option>
          <option value="medical_director">Medical Director</option>
          <option value="cliniko">Cliniko</option>
        </select>
        <button
          onClick={handleSearch}
          disabled={isSearching}
          className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
        >
          {isSearching ? 'Searching...' : 'Search Patient'}
        </button>
      </div>

      {searchResults.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] text-stone-500">{searchResults.length} patient(s) found:</p>
          {searchResults.map((patient) => (
            <div
              key={patient.patient_id}
              className="flex items-center justify-between p-2 bg-white border border-stone-200 rounded hover:border-amber-300 transition-colors"
            >
              <div>
                <p className="text-xs font-medium text-stone-700">{patient.name}</p>
                <p className="text-[10px] text-stone-400">DOB: {patient.dob} • ID: {patient.patient_id}</p>
              </div>
              <button
                onClick={() => handleLink(patient.patient_id)}
                className="px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-medium rounded transition-colors"
              >
                Link
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Offline Mode Indicator
const OfflineIndicator = ({ isOnline, pendingCount, onSync }) => {
  if (isOnline && pendingCount === 0) return null;

  return (
    <div className={`fixed bottom-4 left-4 z-50 px-4 py-2 rounded-lg shadow-lg flex items-center gap-3 ${isOnline ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
      }`}>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${isOnline ? 'bg-amber-500' : 'bg-red-500 animate-pulse'}`}></span>
        <span className="text-sm font-medium">
          {isOnline ? `${pendingCount} action(s) pending sync` : 'Offline Mode'}
        </span>
      </div>
      {isOnline && pendingCount > 0 && (
        <button
          onClick={onSync}
          className="px-2 py-1 bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium rounded transition-colors"
        >
          Sync Now
        </button>
      )}
    </div>
  );
};

// Sidebar Navigation
const Sidebar = ({ activeFilter, setActiveFilter, stats }) => {
  const navItems = [
    { id: 'all', label: 'All Messages', count: stats.total, icon: '📬' },
    { id: 'critical', label: 'Critical', count: stats.critical, icon: '🚨', highlight: stats.critical > 0, critical: true },
    { id: 'urgent', label: 'High Priority', count: stats.urgent, icon: '🔴', highlight: stats.urgent > 0 },
    { id: 'review', label: 'Needs Review', count: stats.ambiguous, icon: '⚠️', highlight: stats.ambiguous > 0 },
    { id: 'pending', label: 'Pending', count: stats.pending, icon: '⏳' },
    { id: 'actioned', label: 'Actioned', count: stats.actioned, icon: '✓' },
    { id: 'archived', label: 'Archived', count: stats.archived, icon: '📁' },
    { id: 'video', label: 'Product Video', count: null, icon: '🎬', isSpecial: true },
  ];

  return (
    <aside className="w-56 bg-white border-r border-stone-200 flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-stone-100">
        <h1 className="text-lg font-semibold text-stone-800">
          Heidi<span className="text-amber-600">Calls</span>
        </h1>
        <p className="text-[11px] text-stone-400 mt-0.5">Voicemail Triage</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-0.5">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveFilter(item.id)}
            className={`
              w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors
              ${activeFilter === item.id
                ? item.critical
                  ? 'bg-red-50 text-red-800 font-medium'
                  : 'bg-amber-50 text-amber-800 font-medium'
                : 'text-stone-600 hover:bg-stone-50'}
            `}
          >
            <span className="flex items-center gap-2.5">
              <span className="text-base">{item.icon}</span>
              <span>{item.label}</span>
            </span>
            <span className={`
              text-xs px-1.5 py-0.5 rounded-full min-w-[20px] text-center
              ${item.critical && item.count > 0
                ? 'bg-red-500 text-white font-bold animate-pulse'
                : item.highlight
                  ? 'bg-red-100 text-red-700 font-medium'
                  : 'bg-stone-100 text-stone-500'}
            `}>
              {item.count}
            </span>
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-stone-100">
        <div className="text-[10px] text-stone-400 text-center">
          Updated {new Date().toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </aside>
  );
};

// Product Video Page
const ProductVideoPage = () => {
  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-amber-500 to-orange-500 px-6 py-8 text-white">
          <h1 className="text-2xl font-bold mb-2">Heidi Calls Product Demo</h1>
          <p className="text-amber-100">See how Heidi Calls transforms your medical practice's voicemail management</p>
        </div>

        {/* Video Player */}
        <div className="p-6">
          <div className="aspect-video bg-stone-900 rounded-xl overflow-hidden shadow-inner">
            <video
              controls
              className="w-full h-full"
              poster=""
            >
              <source src="/heidi.mp4" type="video/mp4" />
              Your browser does not support the video tag.
            </video>
          </div>

          {/* Video Description */}
          <div className="mt-6 space-y-4">
            <h2 className="text-lg font-semibold text-stone-800">About Heidi Calls</h2>
            <p className="text-stone-600 leading-relaxed">
              Heidi Calls is an intelligent voicemail triage system designed specifically for healthcare clinics.
              It automatically transcribes, categorizes, and prioritizes patient voicemails, helping your staff
              respond to urgent cases faster while maintaining HIPAA compliance.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
              <div className="bg-amber-50 rounded-lg p-4 text-center">
                <div className="text-2xl mb-1">🎯</div>
                <div className="text-xs font-medium text-stone-700">Smart Triage</div>
              </div>
              <div className="bg-emerald-50 rounded-lg p-4 text-center">
                <div className="text-2xl mb-1">🔒</div>
                <div className="text-xs font-medium text-stone-700">PII Protection</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <div className="text-2xl mb-1">🚨</div>
                <div className="text-xs font-medium text-stone-700">Emergency Alerts</div>
              </div>
              <div className="bg-purple-50 rounded-lg p-4 text-center">
                <div className="text-2xl mb-1">📊</div>
                <div className="text-xs font-medium text-stone-700">Analytics</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Morning Summary Card - Shows overnight stats
const MorningSummary = ({ voicemails, onFilterClick }) => {
  const overnight = voicemails.filter(v => {
    const created = new Date(v.created_at);
    const now = new Date();
    const hoursAgo = (now - created) / (1000 * 60 * 60);
    return hoursAgo <= 12; // Last 12 hours
  });

  const needsAction = voicemails.filter(v => v.status === 'pending' || v.status === 'processed');
  const criticalCount = needsAction.filter(v => v.urgency.level >= 5).length;
  const urgentCount = needsAction.filter(v => v.urgency.level === 4).length;
  const reviewCount = needsAction.filter(v => v.intent === 'Ambiguous' || v.ui_state?.is_ambiguous).length;

  // Calculate oldest waiting item
  const oldestPending = needsAction.length > 0
    ? needsAction.reduce((oldest, v) => new Date(v.created_at) < new Date(oldest.created_at) ? v : oldest)
    : null;

  const oldestWait = oldestPending ? getWaitingTimeWithSLA(oldestPending.created_at, oldestPending.urgency.level) : null;

  if (needsAction.length === 0) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mb-4">
        <div className="flex items-center gap-3">
          <span className="text-2xl">✨</span>
          <div>
            <h3 className="font-medium text-emerald-800">All Clear!</h3>
            <p className="text-sm text-emerald-600">No pending voicemails. Great job!</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-stone-200 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-stone-800 flex items-center gap-2">
          <span>☀️</span> Morning Summary
        </h3>
        <span className="text-xs text-stone-400">
          {overnight.length} new overnight
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {/* Critical */}
        <button
          onClick={() => onFilterClick('critical')}
          className={`p-3 rounded-lg text-center transition-colors ${criticalCount > 0 ? 'bg-red-50 hover:bg-red-100' : 'bg-stone-50'
            }`}
        >
          <div className={`text-2xl font-bold ${criticalCount > 0 ? 'text-red-600' : 'text-stone-300'}`}>
            {criticalCount}
          </div>
          <div className={`text-[10px] uppercase tracking-wide ${criticalCount > 0 ? 'text-red-600' : 'text-stone-400'}`}>
            Critical
          </div>
        </button>

        {/* Urgent */}
        <button
          onClick={() => onFilterClick('urgent')}
          className={`p-3 rounded-lg text-center transition-colors ${urgentCount > 0 ? 'bg-orange-50 hover:bg-orange-100' : 'bg-stone-50'
            }`}
        >
          <div className={`text-2xl font-bold ${urgentCount > 0 ? 'text-orange-600' : 'text-stone-300'}`}>
            {urgentCount}
          </div>
          <div className={`text-[10px] uppercase tracking-wide ${urgentCount > 0 ? 'text-orange-600' : 'text-stone-400'}`}>
            High Priority
          </div>
        </button>

        {/* Needs Review */}
        <button
          onClick={() => onFilterClick('review')}
          className={`p-3 rounded-lg text-center transition-colors ${reviewCount > 0 ? 'bg-amber-50 hover:bg-amber-100' : 'bg-stone-50'
            }`}
        >
          <div className={`text-2xl font-bold ${reviewCount > 0 ? 'text-amber-600' : 'text-stone-300'}`}>
            {reviewCount}
          </div>
          <div className={`text-[10px] uppercase tracking-wide ${reviewCount > 0 ? 'text-amber-600' : 'text-stone-400'}`}>
            Review
          </div>
        </button>

        {/* Total Pending */}
        <button
          onClick={() => onFilterClick('pending')}
          className="p-3 rounded-lg text-center bg-stone-50 hover:bg-stone-100 transition-colors"
        >
          <div className="text-2xl font-bold text-stone-700">
            {needsAction.length}
          </div>
          <div className="text-[10px] uppercase tracking-wide text-stone-500">
            Total Queue
          </div>
        </button>
      </div>

      {/* Oldest waiting */}
      {oldestWait && (
        <div className={`mt-3 pt-3 border-t border-stone-100 flex items-center justify-between text-xs ${oldestWait.isBreached ? 'text-red-600' : oldestWait.isWarning ? 'text-amber-600' : 'text-stone-500'
          }`}>
          <span>Longest waiting:</span>
          <span className={`font-medium ${oldestWait.isBreached ? 'bg-red-100 px-2 py-0.5 rounded' : ''}`}>
            {oldestWait.text}
            {oldestWait.isBreached && ' - SLA BREACHED'}
          </span>
        </div>
      )}
    </div>
  );
};

// Advanced Filter Panel
const AdvancedFilterPanel = ({ filters, setFilters, onApply, onClear }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasActiveFilters = filters.phone || filters.symptom || filters.medication || filters.doctor;

  return (
    <div className="bg-stone-50 border-b border-stone-200">
      {/* Toggle Button */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-6 py-2 flex items-center justify-between text-xs text-stone-600 hover:bg-stone-100 transition-colors"
      >
        <span className="flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          Advanced Filters
          {hasActiveFilters && (
            <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded text-[10px] font-medium">
              Active
            </span>
          )}
        </span>
        <svg className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Filter Panel */}
      {isExpanded && (
        <div className="px-6 py-4 border-t border-stone-200 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Phone Filter */}
            <div>
              <label className="block text-[10px] font-medium text-stone-500 uppercase tracking-wide mb-1">
                Phone Number
              </label>
              <input
                type="text"
                placeholder="e.g. 789"
                value={filters.phone}
                onChange={(e) => setFilters({ ...filters, phone: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-amber-300"
              />
            </div>

            {/* Symptom Filter */}
            <div>
              <label className="block text-[10px] font-medium text-stone-500 uppercase tracking-wide mb-1">
                Symptom
              </label>
              <input
                type="text"
                placeholder="e.g. chest pain"
                value={filters.symptom}
                onChange={(e) => setFilters({ ...filters, symptom: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-amber-300"
              />
            </div>

            {/* Medication Filter */}
            <div>
              <label className="block text-[10px] font-medium text-stone-500 uppercase tracking-wide mb-1">
                Medication
              </label>
              <input
                type="text"
                placeholder="e.g. blood pressure"
                value={filters.medication}
                onChange={(e) => setFilters({ ...filters, medication: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-amber-300"
              />
            </div>

            {/* Doctor Filter */}
            <div>
              <label className="block text-[10px] font-medium text-stone-500 uppercase tracking-wide mb-1">
                Doctor
              </label>
              <input
                type="text"
                placeholder="e.g. Dr Wong"
                value={filters.doctor}
                onChange={(e) => setFilters({ ...filters, doctor: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border border-stone-200 rounded focus:outline-none focus:ring-1 focus:ring-amber-300"
              />
            </div>
          </div>

          {/* Hide Old Actioned Toggle */}
          <div className="flex items-center justify-between pt-2 border-t border-stone-200">
            <label className="flex items-center gap-2 text-xs text-stone-600 cursor-pointer">
              <input
                type="checkbox"
                checked={filters.hideOldActioned}
                onChange={(e) => setFilters({ ...filters, hideOldActioned: e.target.checked })}
                className="rounded border-stone-300 text-amber-600 focus:ring-amber-500"
              />
              Auto-hide actioned items older than 48 hours
            </label>

            <div className="flex items-center gap-2">
              <button
                onClick={onClear}
                className="px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-200 rounded transition-colors"
              >
                Clear All
              </button>
              <button
                onClick={onApply}
                className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-700 text-white font-medium rounded transition-colors"
              >
                Apply Filters
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Header
const Header = ({ searchQuery, setSearchQuery, resultCount, filters, setFilters, onApplyFilters, onClearFilters }) => (
  <header className="bg-white border-b border-stone-200 sticky top-0 z-10">
    <div className="px-6 py-3 flex items-center justify-between">
      <div>
        <h2 className="text-base font-medium text-stone-800">Voicemail Queue</h2>
        <p className="text-xs text-stone-400">
          {new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' })}
          <span className="mx-2">·</span>
          <span className="text-stone-500">{resultCount} messages</span>
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <input
          type="text"
          placeholder="Search messages..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-64 pl-9 pr-4 py-2 bg-stone-50 border border-stone-200 rounded-lg text-sm text-stone-700 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-amber-200 focus:border-amber-300"
        />
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
    </div>

    {/* Advanced Filters */}
    <AdvancedFilterPanel
      filters={filters}
      setFilters={setFilters}
      onApply={onApplyFilters}
      onClear={onClearFilters}
    />
  </header>
);

// Single Voicemail Card - High Density Layout with Emergency UI
const VoicemailCard = ({ voicemail, isExpanded, onToggle, onStatusChange, onVoicemailUpdate }) => {
  const isAmbiguous = voicemail.intent === 'Ambiguous' || voicemail.ui_state?.is_ambiguous;
  const needsManualListening = voicemail.ui_state?.needs_manual_listening;
  const urgencyConfig = getUrgencyConfig(voicemail.urgency.level, isAmbiguous);
  const statusConfig = getStatusConfig(voicemail.status);
  const intentConfig = getIntentConfig(voicemail.intent);
  const isUrgent = voicemail.urgency.level >= 4 && !isAmbiguous;
  const isCritical = voicemail.urgency.level >= 5 && !isAmbiguous;
  const requiresInterpreter = voicemail.language_info?.requires_interpreter;
  const confidence = voicemail.urgency.confidence ?? 1.0;
  const isLowConfidence = confidence < 0.6;
  const hasEscalation = voicemail.escalation?.escalation_triggered;

  // Get callback number from extracted entities
  const callbackNumber = voicemail.extracted_entities?.callback_number;
  const callbackNumberMasked = voicemail.extracted_entities?.callback_number_raw;

  // Calculate waiting time with SLA status (only for pending/processed items)
  const isPending = voicemail.status === 'pending' || voicemail.status === 'processed';
  const waitingTime = isPending ? getWaitingTimeWithSLA(voicemail.created_at, voicemail.urgency.level) : null;

  return (
    <div
      className={`
        bg-white rounded-lg border overflow-hidden transition-all duration-200
        ${isAmbiguous
          ? 'border-stone-300 border-dashed'
          : isCritical
            ? 'border-red-300 shadow-lg ring-2 ring-red-100'
            : isUrgent
              ? 'border-stone-200 shadow-sm'
              : 'border-stone-200'}
        ${isExpanded ? 'shadow-md' : 'hover:shadow-sm'}
      `}
    >
      {/* Card with accent bar */}
      <div className="flex">
        {/* Vertical Accent Bar - Pulsing for Critical */}
        <div
          className={`w-1.5 flex-shrink-0 ${isAmbiguous ? 'bg-stone-300' : ''} ${isCritical ? 'animate-pulse' : ''}`}
          style={{ backgroundColor: isAmbiguous ? undefined : urgencyConfig.accentColor }}
        />

        {/* Card Content */}
        <div className="flex-1">
          {/* Escalation Banner for Level 5 */}
          {hasEscalation && <EscalationBanner escalation={voicemail.escalation} />}

          <div className="p-3">
            {/* Header Row - Compact */}
            <div
              className="flex items-start justify-between gap-3 cursor-pointer"
              onClick={onToggle}
            >
              <div className="flex-1 min-w-0">
                {/* Top line: Intent, Time, Location, Language */}
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  {isAmbiguous && (
                    <span className="text-amber-500 text-sm">⚠️</span>
                  )}
                  <span className="text-sm">{intentConfig.icon}</span>
                  <span className="text-xs font-medium text-stone-700">{intentConfig.label}</span>
                  <span className="text-stone-300">·</span>
                  {/* Time with SLA indicator */}
                  {waitingTime ? (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${waitingTime.isBreached
                        ? 'bg-red-100 text-red-700 font-medium'
                        : waitingTime.isWarning
                          ? 'bg-amber-100 text-amber-700'
                          : 'text-stone-400'
                      }`}>
                      ⏱ {waitingTime.text}
                      {waitingTime.isBreached && ' !'}
                    </span>
                  ) : (
                    <span className="text-xs text-stone-400">{getTimeSince(voicemail.created_at)}</span>
                  )}
                  {/* Location Badge */}
                  {voicemail.location_info?.assigned_location && (
                    <>
                      <span className="text-stone-300">·</span>
                      <LocationBadge locationInfo={voicemail.location_info} />
                    </>
                  )}
                  {requiresInterpreter && (
                    <>
                      <span className="text-stone-300">·</span>
                      <span className="text-[10px] px-1.5 py-0.5 bg-violet-50 text-violet-600 rounded font-medium">
                        {voicemail.language} 🌐
                      </span>
                    </>
                  )}
                  {!requiresInterpreter && voicemail.language !== 'English' && (
                    <>
                      <span className="text-stone-300">·</span>
                      <span className="text-xs text-stone-400">{voicemail.language}</span>
                    </>
                  )}
                </div>

                {/* Summary */}
                <p className={`text-sm leading-relaxed ${isAmbiguous ? 'text-stone-500 italic' : isCritical ? 'text-red-800 font-semibold' : isUrgent ? 'text-stone-800 font-medium' : 'text-stone-600'}`}>
                  {voicemail.summary}
                </p>

                {/* Meta Row - Patient Match, Medicare, Phone, Repeat Caller, Callback Status */}
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  {/* Repeat Caller Badge */}
                  <RepeatCallerBadge
                    callCount={voicemail.call_count_today}
                    isRepeatCaller={voicemail.is_repeat_caller}
                    relatedIds={voicemail.related_voicemail_ids}
                  />
                  {/* Callback Status Badge */}
                  <CallbackStatusBadge status={voicemail.callback_status} />
                  {/* PMS Linked Badge */}
                  {voicemail.pms_linked && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded flex items-center gap-1">
                      ✓ PMS
                    </span>
                  )}
                  {/* Patient Match Badge */}
                  {voicemail.patient_match?.medicare_matched && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded flex items-center gap-1">
                      ✅ Medicare Matched
                    </span>
                  )}
                  {/* Medicare Number with Privacy Toggle */}
                  {voicemail.extracted_entities?.medicare_number_masked && (
                    <MedicareDisplay
                      masked={voicemail.extracted_entities.medicare_number_masked}
                      full={voicemail.extracted_entities.medicare_number}
                    />
                  )}
                  {/* Doctor Mentioned */}
                  {voicemail.extracted_entities?.mentioned_doctor && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">
                      👨‍⚕️ {voicemail.extracted_entities.mentioned_doctor}
                    </span>
                  )}
                  <span className="text-[11px] text-stone-300 font-mono">{voicemail.caller_phone_redacted}</span>
                  {isLowConfidence && (
                    <>
                      <span className="text-stone-200">·</span>
                      <ConfidenceIndicator confidence={confidence} />
                    </>
                  )}
                </div>
              </div>

              {/* Right side: Badges */}
              <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                {/* Critical Badge with animation */}
                {isCritical && (
                  <span className="text-[11px] font-bold px-2 py-1 rounded bg-red-600 text-white animate-pulse">
                    🚨 CRITICAL
                  </span>
                )}

                {/* Urgency Badge - Only for urgent (not critical) */}
                {isUrgent && !isCritical && (
                  <span
                    className="text-[11px] font-semibold px-2 py-0.5 rounded"
                    style={{ color: urgencyConfig.textColor, backgroundColor: urgencyConfig.bgColor }}
                  >
                    {urgencyConfig.label.toUpperCase()}
                  </span>
                )}

                {/* Manual Review Flag */}
                {needsManualListening && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded flex items-center gap-1" title="Heavy accent detected - AI transcription may be inaccurate">
                    🎧 Accent - Verify
                  </span>
                )}

                {/* Status Badge */}
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{ color: statusConfig.color, backgroundColor: statusConfig.bgColor }}
                >
                  {statusConfig.label}
                </span>

                {/* Expand Icon */}
                <svg
                  className={`w-4 h-4 text-stone-400 transition-transform mt-0.5 ${isExpanded ? 'rotate-180' : ''}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>

            {/* Expanded Content */}
            {isExpanded && (
              <div className="mt-3 pt-3 border-t border-stone-100 space-y-3">
                {/* Escalation Timeout Alert - Pulsing for unacknowledged Level 5 */}
                {hasEscalation && !voicemail.escalation_acknowledged && (
                  <EscalationTimeoutAlert
                    voicemail={voicemail}
                    onAcknowledge={onVoicemailUpdate}
                  />
                )}

                {/* Action Item with Click-to-Call */}
                <div className={`rounded-lg p-3 ${isCritical ? 'bg-red-50 border border-red-200' : isAmbiguous ? 'bg-amber-50 border border-amber-100' : 'bg-amber-50/70'}`}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <h4 className={`text-[11px] font-medium uppercase tracking-wide mb-1 ${isCritical ? 'text-red-800' : 'text-amber-800'}`}>
                        {isCritical ? '🚨 EMERGENCY ACTION REQUIRED' : isAmbiguous ? '⚠️ Manual Review Required' : 'Recommended Action'}
                      </h4>
                      <p className={`text-sm ${isCritical ? 'text-red-900 font-medium' : 'text-stone-700'}`}>{voicemail.action_item}</p>
                    </div>
                    {callbackNumber && (
                      <PhoneButton phone={callbackNumber} phoneMasked={callbackNumberMasked} />
                    )}
                  </div>

                  {/* Emergency Forward Button for Critical */}
                  {isCritical && (
                    <div className="mt-3 pt-3 border-t border-red-200 flex items-center gap-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); onStatusChange(voicemail.voicemail_id, 'actioned'); }}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-bold rounded-lg transition-colors flex items-center gap-2 shadow-lg"
                      >
                        ⚡ CONFIRM & FORWARD TO EMERGENCY
                      </button>
                      {voicemail.escalation?.emergency_script && (
                        <ListenButton script={voicemail.escalation.emergency_script} />
                      )}
                    </div>
                  )}

                  {/* Accent Warning for Manual Review Cases */}
                  {needsManualListening && !isCritical && (
                    <div className="mt-3 pt-3 border-t border-amber-200">
                      <div className="flex items-center gap-2 text-amber-700">
                        <span className="text-lg">🗣️</span>
                        <div>
                          <p className="text-xs font-medium">Heavy Accent Detected</p>
                          <p className="text-[11px] text-amber-600">AI transcription may be inaccurate. Please listen to the original recording below to verify the content and urgency level.</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Extracted Entities */}
                {voicemail.extracted_entities && (
                  <div className="flex flex-wrap gap-2">
                    {voicemail.extracted_entities.symptoms?.length > 0 && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-stone-400 uppercase">Symptoms:</span>
                        {voicemail.extracted_entities.symptoms.map((s, i) => (
                          <span key={i} className="text-[11px] px-1.5 py-0.5 bg-red-50 text-red-700 rounded">{s}</span>
                        ))}
                      </div>
                    )}
                    {voicemail.extracted_entities.medication_names?.length > 0 && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-stone-400 uppercase">Medications:</span>
                        {voicemail.extracted_entities.medication_names.map((m, i) => (
                          <span key={i} className="text-[11px] px-1.5 py-0.5 bg-violet-50 text-violet-700 rounded">{m}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Routing & Patient Info */}
                {(voicemail.location_info || voicemail.patient_match) && (
                  <div className="bg-stone-50 rounded-lg p-3 space-y-2">
                    <h4 className="text-[10px] font-medium text-stone-400 uppercase tracking-wide">Routing & Patient Info</h4>
                    <div className="flex flex-wrap gap-3 text-xs">
                      {voicemail.location_info?.assigned_location && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-stone-500">Clinic:</span>
                          <LocationBadge locationInfo={voicemail.location_info} />
                          <span className="text-[10px] text-stone-400">
                            ({voicemail.location_info.routing_reason.replace('_', ' ')})
                          </span>
                        </div>
                      )}
                      {voicemail.patient_match?.medicare_matched && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-stone-500">Patient ID:</span>
                          <span className="font-mono text-stone-700">{voicemail.patient_match.patient_id}</span>
                          <span className="text-emerald-600">✓ Verified</span>
                        </div>
                      )}
                      {voicemail.extracted_entities?.mentioned_doctor && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-stone-500">Requested:</span>
                          <span className="text-blue-700">{voicemail.extracted_entities.mentioned_doctor}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Callback Tracking & PMS Integration */}
                <div className="flex flex-wrap gap-3">
                  <CallbackTrackingPanel
                    voicemail={voicemail}
                    onCallbackRecorded={onVoicemailUpdate}
                  />
                  <PMSLinkPanel
                    voicemail={voicemail}
                    onPMSLinked={onVoicemailUpdate}
                  />
                </div>

                {/* AI Reasoning */}
                <div>
                  <h4 className="text-[10px] font-medium text-stone-400 uppercase tracking-wide mb-1">Triage Reasoning</h4>
                  <div className="flex items-center gap-3">
                    <p className="text-xs text-stone-500 italic flex-1">{voicemail.urgency.reasoning}</p>
                    <ConfidenceIndicator confidence={confidence} />
                  </div>
                </div>

                {/* Original Recording Playback */}
                <div className={`rounded-lg p-3 ${needsManualListening ? 'bg-amber-50/70 border border-amber-200' : 'bg-blue-50/50 border border-blue-100'}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className={`text-[10px] font-medium uppercase tracking-wide mb-1 ${needsManualListening ? 'text-amber-700' : 'text-blue-700'}`}>
                        {needsManualListening ? 'Listen to Verify Accent' : 'Original Recording'}
                      </h4>
                      <p className="text-[11px] text-stone-500">
                        {needsManualListening
                          ? 'Heavy accent detected. Listen carefully to verify the transcription accuracy.'
                          : 'Listen to the original voicemail to verify AI triage accuracy'}
                      </p>
                    </div>
                    <VoicemailAudioPlayer
                      transcript={voicemail.redacted_transcript}
                      voicemailId={voicemail.voicemail_id}
                      languageCode={voicemail.language_info?.code || 'en'}
                      isAccentCase={needsManualListening}
                    />
                  </div>
                </div>

                {/* Transcript */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-[10px] font-medium text-stone-400 uppercase tracking-wide">Transcript</h4>
                    {needsManualListening && (
                      <span className="text-[9px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                        Highlighted words are uncertain - hover for alternatives
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-stone-600 bg-stone-50 p-2.5 rounded leading-relaxed font-mono">
                    {needsManualListening ? (
                      <TranscriptWithUncertainty transcript={voicemail.redacted_transcript} />
                    ) : (
                      voicemail.redacted_transcript
                    )}
                  </div>
                  {needsManualListening && <TranscriptLegend />}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 pt-1">
                  {!isCritical && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onStatusChange(voicemail.voicemail_id, 'actioned'); }}
                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors"
                    >
                      ✓ Mark Actioned
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); onStatusChange(voicemail.voicemail_id, 'pending'); }}
                    className="px-3 py-1.5 bg-white hover:bg-stone-50 text-stone-600 text-xs font-medium rounded border border-stone-200 transition-colors"
                  >
                    Return to Queue
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onStatusChange(voicemail.voicemail_id, 'archived'); }}
                    className="px-3 py-1.5 bg-white hover:bg-stone-50 text-stone-500 text-xs rounded border border-stone-200 transition-colors"
                  >
                    Archive
                  </button>
                  <div className="flex-1" />
                  <span className="text-[10px] text-stone-300 font-mono">{voicemail.voicemail_id}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Empty State
const EmptyState = ({ message }) => (
  <div className="text-center py-12">
    <div className="text-4xl mb-3 opacity-50">📭</div>
    <p className="text-stone-500">{message}</p>
  </div>
);

// Loading State
const LoadingState = () => (
  <div className="text-center py-12">
    <div className="inline-block w-6 h-6 border-2 border-amber-300 border-t-amber-600 rounded-full animate-spin mb-3" />
    <p className="text-sm text-stone-500">Loading voicemails...</p>
  </div>
);

// Error State
const ErrorState = ({ message, onRetry }) => (
  <div className="text-center py-12">
    <div className="text-3xl mb-3">⚠️</div>
    <p className="text-red-600 text-sm mb-3">{message}</p>
    <button
      onClick={onRetry}
      className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
    >
      Try Again
    </button>
  </div>
);

// ============================================================================
// MAIN APPLICATION
// ============================================================================
function HeidiCallsDashboardInner() {
  const [voicemails, setVoicemails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [activeFilter, setActiveFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingActions, setPendingActions] = useState([]);
  const toast = useToast();

  // Advanced filters state
  const [advancedFilters, setAdvancedFilters] = useState({
    phone: '',
    symptom: '',
    medication: '',
    doctor: '',
    hideOldActioned: true,
  });

  // Online/Offline detection
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      toast?.addToast('Back online! Syncing changes...', 'success');
      syncPendingActions();
    };
    const handleOffline = () => {
      setIsOnline(false);
      toast?.addToast('You are offline. Changes will sync when reconnected.', 'info');
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Load any pending actions from storage
    setPendingActions(offlineStorage.getPendingActions());

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Sync pending actions when back online
  const syncPendingActions = async () => {
    const actions = offlineStorage.getPendingActions();
    if (actions.length === 0) return;

    for (const action of actions) {
      try {
        if (action.type === 'status_change') {
          await api.updateVoicemail(action.id, { status: action.status });
        } else if (action.type === 'callback') {
          await api.recordCallback(action.id, action.callback_status, action.callback_by, action.notes);
        }
      } catch (err) {
        console.error('Failed to sync action:', action, err);
      }
    }

    offlineStorage.clearActions();
    setPendingActions([]);
    loadVoicemails(); // Refresh data
    toast?.addToast('All changes synced!', 'success');
  };

  // Load voicemails from API on initial load
  useEffect(() => {
    loadVoicemails(advancedFilters);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadVoicemails = async (filters = advancedFilters) => {
    try {
      setLoading(true);
      setError(null);

      // Build query params with advanced filters
      const params = { page_size: 100 };
      if (filters.phone) params.phone = filters.phone;
      if (filters.symptom) params.symptom = filters.symptom;
      if (filters.medication) params.medication = filters.medication;
      if (filters.doctor) params.doctor = filters.doctor;
      params.hide_old_actioned = filters.hideOldActioned;

      const data = await api.fetchVoicemails(params);
      setVoicemails(data.items);
    } catch (err) {
      setError(err.message);
      toast?.addToast('Failed to load voicemails', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Apply advanced filters
  const handleApplyFilters = () => {
    loadVoicemails(advancedFilters);
  };

  // Clear advanced filters
  const handleClearFilters = () => {
    const clearedFilters = {
      phone: '',
      symptom: '',
      medication: '',
      doctor: '',
      hideOldActioned: true,
    };
    setAdvancedFilters(clearedFilters);
    loadVoicemails(clearedFilters);
  };

  // Calculate stats
  const stats = useMemo(() => ({
    total: voicemails.length,
    critical: voicemails.filter(v => v.urgency.level >= 5 && v.intent !== 'Ambiguous').length,
    urgent: voicemails.filter(v => v.urgency.level === 4 && v.intent !== 'Ambiguous').length,
    ambiguous: voicemails.filter(v => v.intent === 'Ambiguous' || v.ui_state?.is_ambiguous).length,
    pending: voicemails.filter(v => v.status === 'pending' || v.status === 'processed').length,
    actioned: voicemails.filter(v => v.status === 'actioned').length,
    archived: voicemails.filter(v => v.status === 'archived').length,
  }), [voicemails]);

  // Filter voicemails
  const filteredVoicemails = useMemo(() => {
    let filtered = voicemails;

    // Apply sidebar filter
    switch (activeFilter) {
      case 'critical':
        filtered = filtered.filter(v => v.urgency.level >= 5 && v.intent !== 'Ambiguous');
        break;
      case 'urgent':
        filtered = filtered.filter(v => v.urgency.level === 4 && v.intent !== 'Ambiguous');
        break;
      case 'review':
        filtered = filtered.filter(v => v.intent === 'Ambiguous' || v.ui_state?.is_ambiguous);
        break;
      case 'pending':
        filtered = filtered.filter(v => v.status === 'pending' || v.status === 'processed');
        break;
      case 'actioned':
        filtered = filtered.filter(v => v.status === 'actioned');
        break;
      case 'archived':
        filtered = filtered.filter(v => v.status === 'archived');
        break;
    }

    // Apply search
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(v =>
        v.summary.toLowerCase().includes(query) ||
        v.redacted_transcript.toLowerCase().includes(query) ||
        v.intent.toLowerCase().includes(query) ||
        v.language.toLowerCase().includes(query)
      );
    }

    // Sort: critical first, then urgent, then by time
    return filtered.sort((a, b) => {
      const aIsAmbiguous = a.intent === 'Ambiguous' || a.ui_state?.is_ambiguous;
      const bIsAmbiguous = b.intent === 'Ambiguous' || b.ui_state?.is_ambiguous;

      // Ambiguous items go to their own section
      if (aIsAmbiguous !== bIsAmbiguous) return aIsAmbiguous ? 1 : -1;

      // Then by urgency level
      if (b.urgency.level !== a.urgency.level) return b.urgency.level - a.urgency.level;

      // Then by time
      return new Date(b.created_at) - new Date(a.created_at);
    });
  }, [voicemails, activeFilter, searchQuery]);

  // Handle status change with toast feedback (with offline support)
  const handleStatusChange = async (id, newStatus) => {
    const statusLabels = {
      actioned: 'Marked as Actioned',
      archived: 'Archived',
      pending: 'Returned to Queue',
      processed: 'Set to Processed'
    };

    if (!isOnline) {
      // Queue for later sync
      offlineStorage.queueAction({ type: 'status_change', id, status: newStatus });
      setPendingActions(offlineStorage.getPendingActions());
      // Optimistically update local state
      setVoicemails(vms => vms.map(v =>
        v.voicemail_id === id ? { ...v, status: newStatus } : v
      ));
      toast?.addToast(`${statusLabels[newStatus]} (will sync when online)`, 'info');
      return;
    }

    try {
      const updated = await api.updateVoicemail(id, { status: newStatus });
      setVoicemails(vms => vms.map(v => v.voicemail_id === id ? updated : v));
      toast?.addToast(statusLabels[newStatus] || 'Status updated', 'success');
    } catch (err) {
      console.error('Failed to update status:', err);
      toast?.addToast('Failed to update status. Please try again.', 'error');
    }
  };

  // Handle voicemail update from child components (callback, PMS link, escalation ack)
  const handleVoicemailUpdate = (updatedVoicemail) => {
    setVoicemails(vms =>
      vms.map(v => v.voicemail_id === updatedVoicemail.voicemail_id ? updatedVoicemail : v)
    );
  };

  return (
    <div className="min-h-screen bg-[#FFFDF5] text-stone-800 font-sans flex">
      {/* Sidebar */}
      <Sidebar
        activeFilter={activeFilter}
        setActiveFilter={setActiveFilter}
        stats={stats}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-screen">
        <Header
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          resultCount={filteredVoicemails.length}
          filters={advancedFilters}
          setFilters={setAdvancedFilters}
          onApplyFilters={handleApplyFilters}
          onClearFilters={handleClearFilters}
        />

        <main className="flex-1 p-5">
          {/* Product Video Page */}
          {activeFilter === 'video' ? (
            <ProductVideoPage />
          ) : (
            <>
              {/* Morning Summary - Only show on "all" or "pending" filter */}
              {!loading && !error && (activeFilter === 'all' || activeFilter === 'pending') && (
                <MorningSummary
                  voicemails={voicemails}
                  onFilterClick={setActiveFilter}
                />
              )}

              {/* Voicemail List - Compact spacing */}
              <div className="space-y-2">
                {loading && <LoadingState />}

                {error && <ErrorState message={error} onRetry={() => loadVoicemails(advancedFilters)} />}

                {!loading && !error && filteredVoicemails.length === 0 && (
                  <EmptyState message="No messages match your criteria" />
                )}

                {!loading && !error && filteredVoicemails.map(vm => (
                  <VoicemailCard
                    key={vm.voicemail_id}
                    voicemail={vm}
                    isExpanded={expandedId === vm.voicemail_id}
                    onToggle={() => setExpandedId(expandedId === vm.voicemail_id ? null : vm.voicemail_id)}
                    onStatusChange={handleStatusChange}
                    onVoicemailUpdate={handleVoicemailUpdate}
                  />
                ))}
              </div>
            </>
          )}
        </main>
      </div>

      {/* Offline Mode Indicator */}
      <OfflineIndicator
        isOnline={isOnline}
        pendingCount={pendingActions.length}
        onSync={syncPendingActions}
      />
    </div>
  );
}

// Wrap with ToastProvider
export default function HeidiCallsDashboard() {
  return (
    <ToastProvider>
      <HeidiCallsDashboardInner />
    </ToastProvider>
  );
}
