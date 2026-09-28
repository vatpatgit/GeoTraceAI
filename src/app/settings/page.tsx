"use client";

import React, { useState } from "react";

export default function SettingsPage() {
    const [apiKey, setApiKey] = useState("••••••••••••••••••••••••");
    const [showKey, setShowKey] = useState(false);
    const [emailAlerts, setEmailAlerts] = useState(true);
    const [confidenceThreshold, setConfidenceThreshold] = useState(75);

    return (
        <div className="min-h-screen bg-[#0b0f17] text-slate-100 p-8">
            <div className="max-w-4xl mx-auto space-y-6">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight text-white">System Settings</h1>
                    <p className="text-sm text-slate-400 mt-1">
                        Configure data feeds, AI detection thresholds, and account preferences.
                    </p>
                </div>

                {/* Account Information */}
                <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow-sm">
                    <h2 className="text-lg font-semibold text-white mb-4">Account Profile</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">
                                Role
                            </label>
                            <input
                                type="text"
                                disabled
                                value="Administrator"
                                className="w-full bg-[#1e293b] border border-slate-700/60 rounded-lg px-3 py-2 text-sm text-slate-300 cursor-not-allowed"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">
                                Admin Email
                            </label>
                            <input
                                type="text"
                                disabled
                                value="admin@terratrack.dev"
                                className="w-full bg-[#1e293b] border border-slate-700/60 rounded-lg px-3 py-2 text-sm text-slate-300 cursor-not-allowed"
                            />
                        </div>
                    </div>
                </div>

                {/* Detection Settings */}
                <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow-sm">
                    <h2 className="text-lg font-semibold text-white mb-4">AI Detection & Monitoring</h2>
                    <div className="space-y-4">
                        <div>
                            <div className="flex justify-between items-center mb-2">
                                <label className="text-sm font-medium text-slate-300">
                                    Minimum Confidence Threshold
                                </label>
                                <span className="text-sm font-semibold text-emerald-400">{confidenceThreshold}%</span>
                            </div>
                            <input
                                type="range"
                                min="50"
                                max="95"
                                value={confidenceThreshold}
                                onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                            />
                        </div>

                        <div className="flex items-center justify-between pt-4 border-t border-slate-800">
                            <div>
                                <p className="text-sm font-medium text-slate-200">Email Notification Feed</p>
                                <p className="text-xs text-slate-400">Receive alerts when severe deforestation is detected</p>
                            </div>
                            <input
                                type="checkbox"
                                checked={emailAlerts}
                                onChange={(e) => setEmailAlerts(e.target.checked)}
                                className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-emerald-500 focus:ring-emerald-500"
                            />
                        </div>
                    </div>
                </div>

                {/* API Key Management */}
                <div className="bg-[#111827] border border-slate-800 rounded-xl p-6 shadow-sm">
                    <h2 className="text-lg font-semibold text-white mb-4">Sentinel-2 Satellite Feed</h2>
                    <div className="space-y-3">
                        <label className="block text-xs font-medium uppercase tracking-wider text-slate-400">
                            Copernicus API Client Secret
                        </label>
                        <div className="flex gap-2">
                            <input
                                type={showKey ? "text" : "password"}
                                readOnly
                                value="sh-client-secret-live-a892bcf741"
                                className="flex-1 bg-[#1e293b] border border-slate-700/60 rounded-lg px-3 py-2 text-sm text-slate-300 font-mono"
                            />
                            <button
                                type="button"
                                onClick={() => setShowKey(!showKey)}
                                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-medium text-slate-200 transition-colors"
                            >
                                {showKey ? "Hide" : "Show"}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}