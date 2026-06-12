# Mythos V - Build system
# Requires: V compiler (https://vlang.io), llama.cpp built from source

V      ?= v
LLAMA  ?= ../llama.cpp
BUILD  ?= build

.PHONY: all clean run chat cloud scan doctor status init model

all: $(BUILD)/mythos

$(BUILD)/mythos: main.v src/**/*.v
	mkdir -p $(BUILD)
	$(V) -cg -d no_backtrace -o $(BUILD)/mythos .

# Debug build with symbols
debug: main.v src/**/*.v
	mkdir -p $(BUILD)
	$(V) -g -o $(BUILD)/mythos .

# Production build (optimized)
prod: main.v src/**/*.v
	mkdir -p $(BUILD)
	$(V) -prod -o $(BUILD)/mythos .

clean:
	rm -rf $(BUILD)

# Convenience targets
run: all
	./$(BUILD)/mythos chat

chat: all
	./$(BUILD)/mythos chat

cloud: all
	./$(BUILD)/mythos cloud

scan: all
	./$(BUILD)/mythos scan

model: all
	./$(BUILD)/mythos model

doctor: all
	./$(BUILD)/mythos doctor

status: all
	./$(BUILD)/mythos status

init: all
	./$(BUILD)/mythos init

# Build with custom llama.cpp path
llama:
	test -d $(LLAMA) || git clone https://github.com/ggerganov/llama.cpp $(LLAMA)
	cd $(LLAMA) && cmake -B build -DGGML_VULKAN=ON && cmake --build build --config Release -j$$(nproc)

# Test
test:
	$(V) test .

# Format
fmt:
	$(V) fmt -w src/
