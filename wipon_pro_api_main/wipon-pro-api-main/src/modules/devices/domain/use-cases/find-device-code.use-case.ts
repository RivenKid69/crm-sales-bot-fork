import { Injectable } from '@nestjs/common';

@Injectable()
export class FindDeviceCodeUseCase {
  handle(deviceCode: string) {
    // TODO: make database query to find device code and throw error if absent
  }
}
