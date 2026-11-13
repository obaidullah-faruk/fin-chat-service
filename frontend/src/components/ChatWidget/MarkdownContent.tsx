import React, { useMemo } from 'react';
import { Box, type SxProps, type Theme } from '@mui/material';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

// Configure marked with GitHub Flavored Markdown and line breaks
marked.setOptions({
  gfm: true,
  breaks: true,
});

// Configure DOMPurify hook so all markdown links open in a new tab securely
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

interface MarkdownContentProps {
  content: string;
  isUser?: boolean;
  sx?: SxProps<Theme>;
}

export const MarkdownContent: React.FC<MarkdownContentProps> = ({
  content,
  isUser = false,
  sx,
}) => {
  const sanitizedHtml = useMemo(() => {
    if (!content) return '';
    try {
      const rawHtml = marked.parse(content) as string;
      return DOMPurify.sanitize(rawHtml, {
        ALLOWED_TAGS: [
          'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike',
          'code', 'pre', 'ul', 'ol', 'li', 'blockquote',
          'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
          'table', 'thead', 'tbody', 'tr', 'th', 'td',
          'a', 'span', 'hr'
        ],
        ALLOWED_ATTR: ['href', 'target', 'rel', 'class'],
      });
    } catch {
      return content;
    }
  }, [content]);

  return (
    <Box
      className="markdown-content"
      dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
      sx={[
        {
          fontSize: '0.875rem',
          lineHeight: 1.55,
          color: 'inherit',
          wordBreak: 'break-word',
          '& p': {
            m: 0,
            mb: 1,
            '&:last-child': { mb: 0 },
          },
          '& strong, & b': {
            fontWeight: 700,
            color: 'inherit',
          },
          '& em, & i': {
            fontStyle: 'italic',
          },
          '& ul, & ol': {
            m: 0,
            mb: 1,
            pl: 2.25,
            '&:last-child': { mb: 0 },
          },
          '& li': {
            mb: 0.5,
            '&:last-child': { mb: 0 },
          },
          '& code': {
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: '0.8125rem',
            bgcolor: isUser ? 'rgba(255, 255, 255, 0.22)' : 'rgba(15, 23, 42, 0.08)',
            color: 'inherit',
            px: 0.6,
            py: 0.2,
            borderRadius: '4px',
          },
          '& pre': {
            bgcolor: isUser ? 'rgba(0, 0, 0, 0.25)' : '#f1f5f9',
            border: isUser ? 'none' : '1px solid #e2e8f0',
            p: 1.25,
            borderRadius: 1.5,
            overflowX: 'auto',
            my: 1,
            '& code': {
              bgcolor: 'transparent',
              p: 0,
              borderRadius: 0,
            },
          },
          '& blockquote': {
            m: 0,
            my: 1,
            pl: 1.5,
            borderLeft: '3px solid',
            borderColor: isUser ? 'rgba(255, 255, 255, 0.5)' : 'primary.light',
            color: 'inherit',
            opacity: 0.9,
          },
          '& table': {
            borderCollapse: 'collapse',
            width: '100%',
            my: 1,
            fontSize: '0.8125rem',
          },
          '& th, & td': {
            border: '1px solid',
            borderColor: isUser ? 'rgba(255, 255, 255, 0.2)' : '#e2e8f0',
            px: 1,
            py: 0.5,
            textAlign: 'left',
          },
          '& th': {
            bgcolor: isUser ? 'rgba(255, 255, 255, 0.15)' : '#f8fafc',
            fontWeight: 600,
          },
          '& a': {
            color: isUser ? '#ffffff' : 'primary.main',
            textDecoration: 'underline',
            fontWeight: 500,
          },
          '& hr': {
            border: 0,
            borderTop: '1px solid',
            borderColor: isUser ? 'rgba(255, 255, 255, 0.2)' : '#e2e8f0',
            my: 1,
          },
          '& h1, & h2, & h3, & h4, & h5, & h6': {
            fontWeight: 700,
            m: 0,
            mb: 0.75,
            color: 'inherit',
          },
          '& h1': { fontSize: '1.15rem' },
          '& h2': { fontSize: '1.05rem' },
          '& h3': { fontSize: '0.95rem' },
          '& h4, & h5, & h6': { fontSize: '0.875rem' },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  );
};

