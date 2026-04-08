class MessageNode:
    def __init__(self, data):
        self.data = data
        self.prev = None
        self.next = None

class LinkedList:
    def __init__(self, data):
        self.head = None
        self.tail = None
        self.size = 0

    def append(self, data):
        new_node = MessageNode(data)
        if self.tail:
            self.tail.next = new_node
            new_node.prev = self.tail
            self.tail = new_node
            if self.head is None:
                self.head = new_node
        self.size += 1

    def get_all(self):
        messages = []
        current = self.head
        while current:
            messages.append(current.data)
            current = current.next
        return messages
    
    def get_last(self, n):
        all_msgs = self.get_all()
        return all_msgs[-n:] if len(all_msgs) >= n else all_msgs
    
    def delete_first(self):
        if self.head is None:
            return None
        data = self.head.data
        self.head = self.head.next
        if self.head:
            self.head.prev = None
        else:
            self.tail = None
            self.size -= 1
            return data

    def __len__(self):
        return self.size