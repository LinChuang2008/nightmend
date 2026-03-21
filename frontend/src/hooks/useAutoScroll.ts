/**
 * 智能自动滚动 Hook
 * AI 处理中自动滚动到底部；用户手动向上滚动后停止；新一轮对话开始时恢复
 */
import { useRef, useCallback, useEffect } from 'react';

export function useAutoScroll(deps: any[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolledUpRef = useRef(false);

  const scrollToBottom = useCallback((force = false) => {
    const el = containerRef.current;
    if (!el) return;
    if (force || !isUserScrolledUpRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  // 监听滚动事件，判断用户是否手动向上滚动
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      isUserScrolledUpRef.current = distanceFromBottom > 100;
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  // 内容变化时自动滚动
  useEffect(() => {
    scrollToBottom();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // 新一轮对话开始时强制滚动到底部并重置状态
  const resetScroll = useCallback(() => {
    isUserScrolledUpRef.current = false;
    scrollToBottom(true);
  }, [scrollToBottom]);

  return { containerRef, scrollToBottom, resetScroll };
}
