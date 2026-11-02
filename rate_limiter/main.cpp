#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <chrono>
#include <sw/redis++/redis++.h>
#include <httplib.h>

using namespace sw::redis;
using namespace std::chrono;
using namespace httplib;

std::string load_script(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open " + path);
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

int main() {
    try {
        auto redis = Redis("tcp://redis:6379");
        std::string script = load_script("token_bucket.lua");
        std::string sha = redis.script_load(script);

        std::cout << "[INIT] Rate Limiter Lua script loaded." << std::endl;

        Server svr;

        // Health check endpoint
        svr.Get("/health", [](const Request& req, Response& res) {
            res.set_content("{\"status\": \"healthy\"}", "application/json");
        });

        // The Circuit Breaker Evaluation Endpoint
        // We capture 'redis' and 'sha' by reference/value so the lambda can use them
        // The Circuit Breaker Evaluation Endpoint
        svr.Get("/check", [&redis, sha, script](const Request& req, Response& res) mutable {
            if (!req.has_param("service")) {
                res.status = 400;
                res.set_content("{\"error\": \"Missing 'service' parameter\"}", "application/json");
                return;
            }

            std::string service = req.get_param_value("service");
            std::string service_key = "rate_limit:" + service;
            std::string config_key = "gatekeeper:config:" + service;

            // 1. Dynamic Configuration Retrieval
            // Fetch the ML-assigned limits from Redis.
            auto cap_opt = redis.hget(config_key, "capacity");
            auto rate_opt = redis.hget(config_key, "rate");

            // Fail-safe defaults: If ML is offline or hasn't scored this service yet, default to safe limits
            std::string capacity = cap_opt ? *cap_opt : "100";
            std::string rate = rate_opt ? *rate_opt : "10";
            std::string requested = "1";

            auto now = duration_cast<seconds>(system_clock::now().time_since_epoch()).count();
            std::string now_str = std::to_string(now);

            // 2. Token Bucket Execution with Lazy Reloading
            try {
                auto result = redis.evalsha<long long>(sha, {service_key}, {capacity, rate, now_str, requested});

                if (result == 1) {
                    res.status = 200;
                    res.set_content("{\"allowed\": true}", "application/json");
                } else {
                    res.status = 429;
                    res.set_content("{\"allowed\": false, \"reason\": \"Circuit Breaker Tripped by ML Control Plane\"}", "application/json");
                }
            } catch (const ReplyError &err) {
                if (std::string(err.what()).find("NOSCRIPT") != std::string::npos) {
                    std::cout << "[WARN] NOSCRIPT detected. Reloading Lua script..." << std::endl;
                    sha = redis.script_load(script);

                    // Retry execution
                    auto result = redis.evalsha<long long>(sha, {service_key}, {capacity, rate, now_str, requested});
                    if (result == 1) {
                        res.status = 200;
                        res.set_content("{\"allowed\": true}", "application/json");
                    } else {
                        res.status = 429;
                        res.set_content("{\"allowed\": false, \"reason\": \"Circuit Breaker Tripped\"}", "application/json");
                    }
                } else {
                    res.status = 500;
                    res.set_content("{\"error\": \"Redis execution failed\"}", "application/json");
                }
            }
        });

        std::cout << "[START] C++ Rate Limiter listening on 0.0.0.0:8080..." << std::endl;
        svr.listen("0.0.0.0", 8080);

    } catch (const std::exception &e) {
        std::cerr << "Fatal Error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}