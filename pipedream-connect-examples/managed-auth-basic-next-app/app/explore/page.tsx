'use client';

import { useState, useEffect } from 'react';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

interface Episode {
  name: string;
  body: string;
  created_at: string;
}

interface Entity {
  name: string;
  summary: string;
  labels: string[];
  created_at: string;
}

interface Relationship {
  source: string;
  type: string;
  target: string;
  fact: string;
}

export default function ExplorePage() {
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [view, setView] = useState<'episodes' | 'entities' | 'relationships'>('episodes');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        const [episodesRes, entitiesRes, relationshipsRes] = await Promise.all([
          fetch(`${BACKEND_URL}/api/explore/episodes?limit=20`),
          fetch(`${BACKEND_URL}/api/explore/entities?limit=50`),
          fetch(`${BACKEND_URL}/api/explore/relationships?limit=50`)
        ]);

        if (!episodesRes.ok || !entitiesRes.ok || !relationshipsRes.ok) {
          throw new Error('Failed to fetch graph data');
        }

        const episodesData = await episodesRes.json();
        const entitiesData = await entitiesRes.json();
        const relationshipsData = await relationshipsRes.json();

        setEpisodes(episodesData.episodes || []);
        setEntities(entitiesData.entities || []);
        setRelationships(relationshipsData.relationships || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg">Loading graph data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-red-600">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Knowledge Graph Explorer</h1>
        <p className="text-gray-600 mb-6">Inspect FalkorDB contents (read-only)</p>

        {/* Tab Switcher */}
        <div className="mb-6 border-b border-gray-200">
          <div className="flex space-x-4">
            <button
              onClick={() => setView('episodes')}
              className={`px-4 py-2 font-medium border-b-2 transition-colors ${
                view === 'episodes'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Episodes ({episodes.length})
            </button>
            <button
              onClick={() => setView('entities')}
              className={`px-4 py-2 font-medium border-b-2 transition-colors ${
                view === 'entities'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Entities ({entities.length})
            </button>
            <button
              onClick={() => setView('relationships')}
              className={`px-4 py-2 font-medium border-b-2 transition-colors ${
                view === 'relationships'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Relationships ({relationships.length})
            </button>
          </div>
        </div>

        {/* Episodes View */}
        {view === 'episodes' && (
          <div className="space-y-4">
            {episodes.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                No episodes found. Run a sync to populate the knowledge graph.
              </div>
            ) : (
              episodes.map((ep, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
                  <div className="flex justify-between items-start mb-3">
                    <h3 className="font-bold text-lg">{ep.name}</h3>
                    <span className="text-xs text-gray-500">{ep.created_at}</span>
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-gray-700 font-mono bg-gray-50 p-4 rounded">
                    {ep.body}
                  </pre>
                </div>
              ))
            )}
          </div>
        )}

        {/* Entities View */}
        {view === 'entities' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {entities.length === 0 ? (
              <div className="col-span-full text-center py-12 text-gray-500">
                No entities found. Run a sync to extract entities from your emails.
              </div>
            ) : (
              entities.map((entity, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                  <h3 className="font-bold text-lg mb-1">{entity.name}</h3>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {entity.labels?.map((label, idx) => (
                      <span
                        key={idx}
                        className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded"
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                  <p className="text-sm text-gray-700">{entity.summary}</p>
                  <span className="text-xs text-gray-400 mt-2 block">{entity.created_at}</span>
                </div>
              ))
            )}
          </div>
        )}

        {/* Relationships View */}
        {view === 'relationships' && (
          <div className="space-y-3">
            {relationships.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                No relationships found. Run a sync to extract entity relationships.
              </div>
            ) : (
              relationships.map((rel, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                  <div className="flex items-center space-x-3 mb-2">
                    <span className="font-semibold text-blue-600">{rel.source}</span>
                    <span className="text-gray-400">→</span>
                    <span className="text-xs bg-gray-100 px-2 py-1 rounded">{rel.type}</span>
                    <span className="text-gray-400">→</span>
                    <span className="font-semibold text-green-600">{rel.target}</span>
                  </div>
                  <p className="text-sm text-gray-700">{rel.fact}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
