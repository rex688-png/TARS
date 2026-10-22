/** Preserve the reader's position unless they were already following the tail. */
export function shouldFollowConversation(scrollHeight: number, scrollTop: number, clientHeight: number): boolean {
    return scrollHeight - scrollTop - clientHeight < 120;
}
