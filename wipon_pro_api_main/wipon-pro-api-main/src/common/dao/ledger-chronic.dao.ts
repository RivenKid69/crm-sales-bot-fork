import { BaseEntity, Column, Entity, PrimaryGeneratedColumn } from 'typeorm';

@Entity('ledger_chronics')
export class LedgerChronicDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'ledger_id' })
  ledger_id: number;

  @Column({ name: 'user_id' })
  user_id: number;

  @Column({ name: 'started_at', type: 'timestamp' })
  started_at: Date;

  @Column({ name: 'finished_at', type: 'timestamp' })
  finished_at: Date;
}
