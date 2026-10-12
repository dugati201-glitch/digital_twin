CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2 -Iinclude
LDFLAGS ?= -lmosquitto -lpthread -lm

SRCS = src/protocol.c src/state.c src/main.c
TARGET = bin/gateway_client

TEST_SRCS = src/protocol.c src/state.c tests/test_c_gateway.c
TEST_TARGET = bin/test_c_gateway

.PHONY: all clean test

all: $(TARGET)

$(TARGET): $(SRCS)
	@mkdir -p bin
	$(CC) $(CFLAGS) -o $@ $(SRCS) $(LDFLAGS)
	@echo "Build successful: $@"

test: $(TEST_TARGET)
	@./$(TEST_TARGET)

$(TEST_TARGET): $(TEST_SRCS)
	@mkdir -p bin
	$(CC) $(CFLAGS) -o $@ $(TEST_SRCS) -lpthread -lm
	@echo "Test build successful: $@"

clean:
	rm -rf bin

