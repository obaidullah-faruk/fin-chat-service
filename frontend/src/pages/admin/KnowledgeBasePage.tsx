import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  CloudUpload as UploadIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Storage as StorageIcon,
  Description as DocIcon,
  FolderZip as ChunksIcon,
  Category as CategoryIcon,
} from '@mui/icons-material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  seedLocalKnowledge,
  uploadKnowledgeDocument,
  type IngestResponse,
  type KnowledgeDocument,
} from '../../api/knowledge';

const CATEGORY_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> = {
  policy: 'primary',
  rates: 'success',
  cards: 'secondary',
  offers: 'warning',
  general: 'default',
};

export function KnowledgeBasePage() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Upload modal state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [docTitle, setDocTitle] = useState('');
  const [docCategory, setDocCategory] = useState('general');

  // Collision dialog state
  const [collisionData, setCollisionData] = useState<IngestResponse | null>(null);

  // Delete dialog state
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDocument | null>(null);

  // Queries
  const { data: documents = [], isLoading, isFetching, refetch } = useQuery({
    queryKey: ['admin-knowledge-documents'],
    queryFn: listKnowledgeDocuments,
  });

  // Seed local data mutation
  const seedMutation = useMutation({
    mutationFn: seedLocalKnowledge,
    onSuccess: (res) => {
      setFeedback({
        type: 'success',
        text: `Successfully synced local banking documents! Indexed ${res.indexed_documents_count} documents (${res.total_chunks_indexed} total chunks in Qdrant).`,
      });
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-documents'] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || err.message || 'Failed to sync local data.';
      setFeedback({ type: 'error', text: msg });
    },
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (variables: { file: File; title?: string; category: string; collisionAction?: 'check' | 'replace' | 'alias' | 'force' }) =>
      uploadKnowledgeDocument(variables.file, variables.title, variables.category, variables.collisionAction),
    onSuccess: (res) => {
      if (res.status === 'collision') {
        setCollisionData(res);
        return;
      }
      setUploadOpen(false);
      setSelectedFile(null);
      setDocTitle('');
      setCollisionData(null);
      setFeedback({
        type: 'success',
        text: `Document '${res.title}' indexed successfully (${res.chunk_count} chunks in Qdrant, v${res.version}).`,
      });
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-documents'] });
    },
    onError: (err: any) => {
      if (err.response?.status === 409 && err.response?.data) {
        setCollisionData(err.response.data);
      } else {
        const msg = err.response?.data?.detail || err.message || 'Document upload failed.';
        setFeedback({ type: 'error', text: msg });
      }
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (docId: string) => deleteKnowledgeDocument(docId),
    onSuccess: () => {
      setDeleteTarget(null);
      setFeedback({ type: 'info', text: 'Document and its vector points purged from Qdrant.' });
      queryClient.invalidateQueries({ queryKey: ['admin-knowledge-documents'] });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || err.message || 'Failed to delete document.';
      setFeedback({ type: 'error', text: msg });
    },
  });

  // Metrics
  const totalChunks = useMemo(() => documents.reduce((acc, doc) => acc + (doc.chunk_count || 0), 0), [documents]);
  const categoriesCount = useMemo(() => new Set(documents.map((d) => d.category)).size, [documents]);

  // Filtered documents
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const matchesCategory = selectedCategory === 'all' || doc.category === selectedCategory;
      const matchesSearch =
        !searchTerm ||
        doc.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        doc.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
        doc.category.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [documents, selectedCategory, searchTerm]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      if (!docTitle) {
        setDocTitle(file.name.replace(/\.[^/.]+$/, '').replace(/_/g, ' '));
      }
    }
  };

  const handleUploadSubmit = () => {
    if (!selectedFile) return;
    uploadMutation.mutate({
      file: selectedFile,
      title: docTitle,
      category: docCategory,
      collisionAction: 'check',
    });
  };

  const handleResolveCollision = (action: 'replace' | 'alias') => {
    if (!selectedFile) return;
    uploadMutation.mutate({
      file: selectedFile,
      title: docTitle,
      category: docCategory,
      collisionAction: action,
    });
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Title & Toolbar */}
      <Stack
        direction="row"
        sx={{
          mb: 3,
          flexWrap: 'wrap',
          gap: 2,
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            Knowledge Base Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage official banking documents, interest rate sheets, card terms, and policies indexed in Qdrant with FastEmbed.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.5}>
          <Button
            variant="outlined"
            startIcon={isFetching ? <CircularProgress size={18} /> : <RefreshIcon />}
            onClick={() => refetch()}
            disabled={isFetching}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            color="secondary"
            startIcon={seedMutation.isPending ? <CircularProgress size={18} /> : <StorageIcon />}
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending}
          >
            {seedMutation.isPending ? 'Syncing...' : 'Sync Local Data'}
          </Button>
          <Button
            variant="contained"
            color="primary"
            startIcon={<UploadIcon />}
            onClick={() => {
              setSelectedFile(null);
              setDocTitle('');
              setUploadOpen(true);
            }}
          >
            Upload Document
          </Button>
        </Stack>
      </Stack>

      {/* Feedback Banner */}
      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)} sx={{ mb: 3 }}>
          {feedback.text}
        </Alert>
      )}

      {/* Metrics Cards */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: 'repeat(4, 1fr)' },
          gap: 2,
          mb: 3,
        }}
      >
        <Card variant="outlined">
          <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <DocIcon color="primary" sx={{ fontSize: 40 }} />
            <Box>
              <Typography variant="caption" color="text.secondary">
                Total Documents
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {documents.length}
              </Typography>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <ChunksIcon color="success" sx={{ fontSize: 40 }} />
            <Box>
              <Typography variant="caption" color="text.secondary">
                Indexed Vector Chunks
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {totalChunks}
              </Typography>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <CategoryIcon color="warning" sx={{ fontSize: 40 }} />
            <Box>
              <Typography variant="caption" color="text.secondary">
                Knowledge Domains
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {categoriesCount} Categories
              </Typography>
            </Box>
          </CardContent>
        </Card>
        <Card variant="outlined">
          <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <StorageIcon color="info" sx={{ fontSize: 40 }} />
            <Box>
              <Typography variant="caption" color="text.secondary">
                Vector Engine / Embedder
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                Qdrant + FastEmbed BGE
              </Typography>
            </Box>
          </CardContent>
        </Card>
      </Box>

      {/* Search & Category Filter Tabs */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <Box sx={{ p: 2, display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            size="small"
            placeholder="Search by title, filename, or category..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            sx={{ minWidth: 320 }}
          />
          <Tabs
            value={selectedCategory}
            onChange={(_, val) => setSelectedCategory(val)}
            textColor="primary"
            indicatorColor="primary"
            sx={{ ml: 'auto' }}
          >
            <Tab label="All" value="all" />
            <Tab label="Policies" value="policy" />
            <Tab label="Interest Rates" value="rates" />
            <Tab label="Cards" value="cards" />
            <Tab label="Offers" value="offers" />
            <Tab label="General" value="general" />
          </Tabs>
        </Box>

        {/* Documents Table */}
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Document Title & Filename</TableCell>
              <TableCell>Category</TableCell>
              <TableCell align="center">Format</TableCell>
              <TableCell align="center">Version</TableCell>
              <TableCell align="center">Chunks in Qdrant</TableCell>
              <TableCell>Content Hash</TableCell>
              <TableCell>Uploaded</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                  <CircularProgress size={32} />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Loading documents from Qdrant...
                  </Typography>
                </TableCell>
              </TableRow>
            ) : filteredDocuments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                  <Typography variant="body1" color="text.secondary">
                    No documents found.
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Click "Sync Local Data" to load the baseline banking corpus, or upload a new file.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              filteredDocuments.map((doc) => (
                <TableRow key={doc.doc_id} hover>
                  <TableCell>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                      {doc.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {doc.filename}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={doc.category.toUpperCase()}
                      color={CATEGORY_COLORS[doc.category] || 'default'}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell align="center">
                    <Chip size="small" label={doc.file_format?.toUpperCase() || 'TXT'} />
                  </TableCell>
                  <TableCell align="center">
                    <Chip size="small" label={`v${doc.version || 1}`} variant="outlined" />
                  </TableCell>
                  <TableCell align="center">
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      {doc.chunk_count}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Tooltip title={doc.content_hash || 'N/A'}>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {doc.content_hash ? `${doc.content_hash.slice(0, 10)}...` : 'N/A'}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary">
                      {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : 'N/A'}
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block' }} color="text.secondary">
                      by {doc.uploaded_by || 'admin'}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => setDeleteTarget(doc)}
                      title="Delete document and purge vectors"
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Upload Dialog */}
      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Upload Knowledge Document</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2.5} sx={{ mt: 1 }}>
            <Box
              sx={{
                border: '2px dashed',
                borderColor: 'divider',
                borderRadius: 2,
                p: 3,
                textAlign: 'center',
                bgcolor: 'action.hover',
                cursor: 'pointer',
              }}
              onClick={() => document.getElementById('file-upload-input')?.click()}
            >
              <input
                id="file-upload-input"
                type="file"
                accept=".pdf,.docx,.txt,.md,.json"
                style={{ display: 'none' }}
                onChange={handleFileChange}
              />
              <UploadIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 1 }} />
              <Typography variant="body1" sx={{ fontWeight: 600 }}>
                {selectedFile ? selectedFile.name : 'Click to select or drag & drop file'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Supported formats: PDF, DOCX, Markdown (.md), Text (.txt), JSON (.json)
              </Typography>
            </Box>

            <TextField
              label="Document Title"
              fullWidth
              size="small"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="e.g. 2026 Promotional CD Ladder Rates"
            />

            <FormControl fullWidth size="small">
              <InputLabel>Category</InputLabel>
              <Select
                value={docCategory}
                label="Category"
                onChange={(e) => setDocCategory(e.target.value)}
              >
                <MenuItem value="policy">Bank Policy & Governance</MenuItem>
                <MenuItem value="rates">Interest Rates & Lending</MenuItem>
                <MenuItem value="cards">Credit & Debit Cards</MenuItem>
                <MenuItem value="offers">Promotional Offers</MenuItem>
                <MenuItem value="general">General Banking</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleUploadSubmit}
            disabled={!selectedFile || uploadMutation.isPending}
            startIcon={uploadMutation.isPending ? <CircularProgress size={18} /> : <UploadIcon />}
          >
            {uploadMutation.isPending ? 'Indexing...' : 'Upload & Index'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Content Collision Alert Dialog */}
      <Dialog open={Boolean(collisionData)} onClose={() => setCollisionData(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ color: 'warning.main' }}>
          Content Collision Detected
        </DialogTitle>
        <DialogContent dividers>
          <Typography variant="body1" sx={{ mb: 2 }}>
            The content of the uploaded file is <strong>identical</strong> to an existing document in Qdrant:
          </Typography>
          <Card variant="outlined" sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Existing Document: {collisionData?.existing_document?.title}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              Filename: {collisionData?.existing_document?.filename} (v{collisionData?.existing_document?.version})
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              Category: {collisionData?.existing_document?.category}
            </Typography>
          </Card>
          <Typography variant="body2" color="text.secondary">
            How would you like to proceed?
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setCollisionData(null)}>Cancel</Button>
          <Button
            variant="outlined"
            onClick={() => handleResolveCollision('alias')}
            disabled={uploadMutation.isPending}
          >
            Link as Alias (No Re-embed)
          </Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => handleResolveCollision('replace')}
            disabled={uploadMutation.isPending}
          >
            Replace Existing (New Version)
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>Confirm Document Deletion</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body1">
            Are you sure you want to delete <strong>{deleteTarget?.title}</strong>?
          </Typography>
          <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>
            This will permanently purge all {deleteTarget?.chunk_count} vector chunks from the Qdrant knowledge base.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.doc_id)}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? 'Purging...' : 'Delete & Purge'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
