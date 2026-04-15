'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { httpClient } from '@/app/infra/http/HttpClient';
import { useSidebarData } from '@/app/home/components/home-sidebar/SidebarDataContext';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

type CustomerDetail = {
  id: string;
  customer_name?: string | null;
  phone?: string | null;
  requirement?: string | null;
  company?: string | null;
  address?: string | null;
  intention?: string | null;
  tags?: string | null;
  sender_name?: string | null;
  session_id: string;
  bot_name: string;
  pipeline_name: string;
  last_conversation_at: string;
  structured_profile?: string | null;
  conversation_count?: number;
};

type CustomerConversation = {
  id: string;
  role: string;
  message_text?: string | null;
  message_content?: string | null;
  timestamp: string;
  sender_name?: string | null;
};

function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map((x) => String(x)).filter(Boolean);
    }
  } catch {
    return raw
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return [];
}

function extractText(raw: string | null | undefined): string {
  if (!raw) return '';
  try {
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return raw;
    const parts = arr
      .map((item) => {
        if (!item || typeof item !== 'object') return '';
        const t = item.type;
        if (t === 'Plain') return item.text || '';
        if (t === 'Image') return '[Image]';
        if (t === 'File') return `[File: ${item.name || 'File'}]`;
        if (t === 'Voice') return '[Voice]';
        return '';
      })
      .filter(Boolean);
    return parts.join('');
  } catch {
    return raw;
  }
}

export default function CustomerDetailContent({ id }: { id: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { customers, setDetailEntityName } = useSidebarData();

  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [conversations, setConversations] = useState<CustomerConversation[]>([]);
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    const current = customers.find((item) => item.id === id);
    setDetailEntityName(current?.name || id);
    return () => setDetailEntityName(null);
  }, [customers, id, setDetailEntityName]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [customerResp, convResp] = await Promise.all([
        httpClient.getCustomer(id),
        httpClient.getCustomerConversations(id, { limit: 500, offset: 0 }),
      ]);
      setDetail(customerResp.customer as CustomerDetail);
      setConversations(convResp.conversations as CustomerConversation[]);
    } catch (error) {
      console.error('Failed to fetch customer detail:', error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredConversations = conversations.filter((item) => {
    if (!searchText.trim()) return true;
    const text = item.message_text || extractText(item.message_content);
    return text.toLowerCase().includes(searchText.toLowerCase());
  });

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner text={t('common.loading')} />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <p>{t('customers.detail.notFound')}</p>
      </div>
    );
  }

  const tags = parseTags(detail.tags);

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">{t('customers.detail.title')}</h1>
        <Button variant="outline" onClick={() => router.push('/home/customers')}>
          {t('customers.detail.backToList')}
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>{t('customers.detail.profileCard')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <div className="text-muted-foreground">{t('customers.columns.customerName')}</div>
              <div>{detail.customer_name || detail.sender_name || '-'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">{t('customers.columns.phone')}</div>
              <div>{detail.phone || '-'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">{t('customers.columns.requirement')}</div>
              <div className="whitespace-pre-wrap">{detail.requirement || '-'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">{t('customers.columns.company')}</div>
              <div>{detail.company || '-'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">{t('customers.columns.intention')}</div>
              <div>{detail.intention || '-'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">{t('customers.columns.tags')}</div>
              <div className="flex flex-wrap gap-1 mt-1">
                {tags.length > 0 ? tags.map((tag) => <Badge key={tag}>{tag}</Badge>) : '-'}
              </div>
            </div>
            <div className="pt-2 border-t text-xs text-muted-foreground space-y-1">
              <div>
                {t('customers.columns.bot')}: {detail.bot_name}
              </div>
              <div>
                {t('customers.columns.pipeline')}: {detail.pipeline_name}
              </div>
              <div>
                {t('customers.columns.lastConversationAt')}:{' '}
                {new Date(detail.last_conversation_at).toLocaleString()}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t('customers.detail.timelineTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="mb-4">
              <Input
                placeholder={t('customers.detail.searchTimelinePlaceholder')}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
            </div>

            <div className="space-y-3">
              {filteredConversations.length === 0 ? (
                <div className="text-sm text-muted-foreground">
                  {t('customers.detail.noConversations')}
                </div>
              ) : (
                filteredConversations.map((item) => {
                  const text = item.message_text || extractText(item.message_content) || '-';
                  const isUser = item.role === 'user';
                  return (
                    <div
                      key={item.id}
                      className={`rounded-lg border p-3 ${
                        isUser ? 'bg-muted/30' : 'bg-blue-50/40 dark:bg-blue-900/10'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1 text-xs">
                        <span className="font-medium">
                          {isUser
                            ? t('customers.detail.roleUser')
                            : t('customers.detail.roleAssistant')}
                        </span>
                        <span className="text-muted-foreground">
                          {new Date(item.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <div className="text-sm whitespace-pre-wrap break-words">{text}</div>
                    </div>
                  );
                })
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
