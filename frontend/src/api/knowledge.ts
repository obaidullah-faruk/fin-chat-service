import { apiClient } from './client';

export interface KnowledgeDocument {
  doc_id: string;
  title: string;
  filename: string;
  category: 'policy' | 'rates' | 'cards' | 'offers' | 'general';
  file_format: string;
  content_hash: string;
  raw_file_hash: string;
  version: number;
  uploaded_at: string;
  uploaded_by: string;
  chunk_count: number;
}

export interface IngestResponse {
  status: 'success' | 'collision';
  message?: string;
  doc_id?: string;
  title?: string;
  filename?: string;
  category?: string;
  version?: number;
  chunk_count?: number;
  content_hash?: string;
  existing_document?: {
    doc_id: string;
    title: string;
    filename: string;
    category: string;
    version: number;
    uploaded_at: string;
  };
}

export interface SeedResponse {
  status: string;
  indexed_documents_count: number;
  total_chunks_indexed: number;
  documents: string[];
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  const res = await apiClient.get<KnowledgeDocument[]>('/admin/knowledge-base/');
  return res.data;
}

export async function uploadKnowledgeDocument(
  file: File,
  title?: string,
  category: string = 'general',
  collisionAction: 'check' | 'replace' | 'alias' | 'force' = 'check'
): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (title) formData.append('title', title);
  formData.append('category', category);
  formData.append('collision_action', collisionAction);

  const res = await apiClient.post<IngestResponse>('/admin/knowledge-base/upload/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return res.data;
}

export async function deleteKnowledgeDocument(docId: string): Promise<void> {
  await apiClient.delete(`/admin/knowledge-base/${docId}/`);
}

export async function seedLocalKnowledge(): Promise<SeedResponse> {
  const res = await apiClient.post<SeedResponse>('/admin/knowledge-base/seed-local/');
  return res.data;
}
