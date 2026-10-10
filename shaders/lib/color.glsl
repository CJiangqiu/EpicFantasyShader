#ifndef EFS_COLOR
#define EFS_COLOR

vec3 toLinear(vec3 color) {
    return pow(max(color, vec3(0.0)), vec3(2.2));
}

vec3 toDisplay(vec3 color) {
    return pow(max(color, vec3(0.0)), vec3(1.0 / 2.2));
}

#endif
